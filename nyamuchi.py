import argparse
import datetime
import io
import math
import sqlite3

import discord
import ffmpeg
from discord.ext import commands
from discord.ext.commands import Context

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!!!!!', intents=intents)

db = sqlite3.Connection('mygo.sqlite')
args = None
episodes_set = \
    {'1-3', '4', '5', '6', '7', '8', '9', '10', '11', '12', '13'}

episodes_list = \
    ['1-3', '4', '5', '6', '7', '8', '9', '10', '11', '12', '13']


# _episode = {v: k for k, v in episodes.items()}


def time_base(s: str) -> float:
    fls = s.split("/")
    return float(fls[0]) / float(fls[1])


def fps(s) -> float:
    fls = s.split("/")
    return float(fls[0]) / float(fls[1])


@bot.command()
async def search(ctx: Context, text: str, episode: str = '*', page: int = 0, score: float = 0.3):
    if episode not in episodes_set and episode != '*':
        await ctx.send(content='集數: ' + '/'.join(episodes_list))
        return

    page = max(page, 0)
    score = max(score, 0.0)
    print(text)
    print(episode)
    print(page)
    print(score)
    start = int(datetime.datetime.now().timestamp() * 1000)
    if episode == '*':
        query = db.cursor().execute(
            "SELECT text, episode, frame FROM sentence \n"
            "WHERE text LIKE ? AND diff_score>=? ORDER BY rowid LIMIT 20 OFFSET ?"
            , [f'%{text}%', score, page * 20])
    else:
        query = db.cursor().execute(
            "SELECT text, episode, frame FROM sentence \n"
            "WHERE episode = ? AND text LIKE ? AND diff_score>=? ORDER BY rowid LIMIT 20 OFFSET ?"
            , [episode, f'%{text}%', score, page * 20])
    result = [
        f'!!!!!frame {x[1]} {x[2]}\n\n{datetime.timedelta(seconds=float(x[2]) / 23.98)}\n{x[0]}\n'
        f'--------------------------'
        for x in query.fetchall()
    ]
    t = int(datetime.datetime.now().timestamp() * 1000 - start)
    line = '\n'
    await ctx.send(content=f'```{line.join(result)}```\n第{page}頁\n{result.__len__()}筆結果')
    pass


@bot.command()
async def gif(ctx: Context, episode: str, start: int, end: int, saturation: float = 1):
    delta = max(start, end) - min(start, end)
    if delta > 240:
        await ctx.send(content='too long')
        return
    if episode not in episodes_set:
        await ctx.send(content='集數: ' + '/'.join(episodes_list))
        return

    filename: str = episode + '.mp4'

    probe_m = ffmpeg.probe(filename=f'{args.videos_dir}{filename}')
    print(probe_m)
    seek: float = float(min(start, end)) / fps(probe_m['streams'][0]['r_frame_rate'])
    seek_end: float = float(max(start, end)) / fps(probe_m['streams'][0]['r_frame_rate'])
    print(seek)
    if start < 0 or start > float(probe_m['streams'][0]['nb_frames']):
        await ctx.send(content='out of range')
        return
    if end < 0 or end > float(probe_m['streams'][0]['nb_frames']):
        await ctx.send(content='out of range')
        return
    if math.isnan(seek) or math.isinf(seek) or math.isnan(seek_end) or math.isinf(seek):
        await ctx.send(content='out of range')
        return
    if start < end:
        palettegen = ffmpeg.input(filename=f'{args.videos_dir}{filename}', ss=seek) \
            .trim(start_frame=0, end_frame=delta + 1) \
            .filter(filter_name='hue', s=saturation) \
            .filter(filter_name='scale', width=-1, height=240) \
            .filter(filter_name='palettegen', stats_mode='diff')
        # XXX : DC compress gif color space incorrectly, this does not work
        # .filter(filter_name='colorspace', range='pc', space='bt709', trc='srgb', primaries='smpte240m') \
        scale = ffmpeg.input(filename=f'{args.videos_dir}{filename}', ss=seek) \
            .filter(filter_name='hue', s=saturation) \
            .filter(filter_name='scale', width=-1, height=240)

        buffer, error = ffmpeg.filter([scale, palettegen], filter_name='paletteuse', dither='floyd_steinberg',
                                      diff_mode='rectangle') \
            .output('pipe:',
                    vframes=delta,
                    format='gif',
                    vcodec='gif'
                    ) \
            .run(capture_stdout=True)
        if error:
            print(error)
            await ctx.send(content='error')
            return
        else:
            g = discord.File(fp=io.BytesIO(buffer), filename=f'{episode}__{start}-{end}.gif')
            await ctx.send(file=g)
            return
        pass
    else:
        # XXX: ffmpeg graph order needed for reverse filter
        i = ffmpeg.input(filename=f'{args.videos_dir}{filename}', ss=seek) \
            .filter(filter_name='scale', width=-1, height=240) \
            .filter(filter_name='hue', s=saturation)
        palettegen = ffmpeg.input(filename=f'{args.videos_dir}{filename}', ss=seek) \
            .trim(start_frame=0, end_frame=delta + 1) \
            .filter(filter_name='scale', width=-1, height=240) \
            .filter(filter_name='hue', s=saturation) \
            .filter(filter_name='reverse') \
            .filter(filter_name='palettegen', stats_mode='diff')
        # .filter(filter_name='colorspace', range='pc', space='bt709', trc='srgb', primaries='smpte240m') \

        # trim is important for reverse performance
        buffer, error = ffmpeg.filter([i, palettegen], filter_name='paletteuse', dither='floyd_steinberg',
                                      diff_mode='rectangle') \
            .trim(start_frame=0, end_frame=delta + 1) \
            .filter(filter_name='reverse') \
            .output('pipe:',
                    vframes=delta,
                    format='gif',
                    vcodec='gif'
                    ) \
            .run(capture_stdout=True)
        if error:
            print(error)
            await ctx.send(content='error')
            return
        else:
            g = discord.File(fp=io.BytesIO(buffer), filename=f'{episode}__{start}-{end}.gif')
            await ctx.send(file=g)
            return
        pass
        # else
    pass


@bot.command()
async def frame(ctx: Context, episode: str, start: int, saturation: float = 1):
    # filename = ''
    if episode not in episodes_set:
        await ctx.send(content='集數: ' + '/'.join(episodes_set))
        return
    filename: str = episode + '.mp4'
    # if filename == '':
    #     await ctx.send(content=','.join(episodes.keys()))
    #     return
    probe_m = ffmpeg.probe(filename=f'{args.videos_dir}{filename}')
    seek: float = float(start) / fps(probe_m['streams'][0]['r_frame_rate'])
    print(seek)
    if math.isnan(seek) or math.isinf(seek):
        await ctx.send(content='out of range')
        return
    if seek < 0 or start > float(probe_m['streams'][0]['nb_frames']):
        await ctx.send(content='out of range')
        return
    buffer, error = ffmpeg.input(filename=f'{args.videos_dir}{filename}', ss=seek) \
        .filter('hue', s=saturation) \
        .output('pipe:',
                vframes=1,
                format='image2',
                vcodec='png') \
        .run(capture_stdout=True)
    if error:
        await ctx.send(content='error')
        return
    else:
        shot = discord.File(fp=io.BytesIO(buffer), filename=f'{episode}__{start}.png')
        await ctx.send(file=shot)
    pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('token')
    parser.add_argument('videos_dir')
    args = parser.parse_args()
    # print(args.token, args.videos_dir)
    # probe = ffmpeg.probe(filename=f'{args.videos_dir}{episodes["1-3"]}')
    #
    # print(probe)
    # timestamp = 2456 / time_base(probe['streams'][0]['r_frame_rate'])
    # print(timestamp)
    bot.run(token=args.token)
