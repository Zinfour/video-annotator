from PIL import Image, ImageDraw
import mpv
import os
from os import listdir
from os.path import isfile, join
import numpy as np
import bisect
import json
import argparse



parser = argparse.ArgumentParser()
parser.add_argument('--annotations', help='path to annotations folder', default='annotations', metavar='PATH')
parser.add_argument('--thumbnails', help='path to categories/thumbnails folder', default='thumbnails', metavar='PATH')
parser.add_argument('--grid', help='width of the grid in boxes', type=int, default=6, metavar='N')
parser.add_argument('--timeline_distortion', help='scaling factor of the timeline', type=float, default=10, metavar='N')
parser.add_argument('--fancy', help='add colorful colors', action="store_true")
parser.add_argument('path')
args = parser.parse_args()

args = parser.parse_args()

grid_n = args.grid_n
timeline_distortion = args.timeline_distortion
fancy = args.fancy
annotations_path = args.annotations
categories_path = args.thumbnails
path = args.path


cuts = []
segment_categories = [None]

current_file = None

categories = {
    None: (0, (100, 100, 100, 0), Image.new('RGBA', (1, 1), (0, 0, 0, 255)))
}

for i, x in enumerate([f for f in listdir(categories_path) if isfile(join(categories_path, f))], 1):
    img = Image.open(join(categories_path, x))
    if fancy:
        pixels = np.array(img)
        filtered = pixels[np.nonzero(pixels[:, :, 3])][:, :3]
        chromas = np.max(filtered, axis=1) - np.min(filtered, axis=1)
        val = filtered[np.argmax(chromas)]
        val = (val[0], val[1], val[2], 255)
    else:
        val = (100, 100, 100, 255)

    filename, _ = os.path.splitext(x)
    categories[filename] = (i, val, img)

player = mpv.MPV(
    video_align_x=-1,
    video_align_y=-1,
    video_margin_ratio_right=0.2,
    video_margin_ratio_bottom=0.1,
    window_dragging='no',
    input_vo_keyboard=True,
    input_default_bindings=True,
    input_conf='disable_doubleclick', # HACK?
)

player.play(path)
player.wait_until_playing()

overlay1 = player.create_image_overlay()
overlay2 = player.create_image_overlay()
overlay3 = player.create_image_overlay()
overlay4 = player.create_image_overlay()


def render_grid():
    osd_dims = player.osd_dimensions
    dst = Image.new('RGBA', (int(osd_dims['mr']), int(
        osd_dims['h'] - osd_dims['mb'])))
    for i, _, img in categories.values():
        width = int(osd_dims['mr']/grid_n)
        height = int(osd_dims['mr']/grid_n)
        img = img.resize(
            (width, height), box=(0, 0, img.size[0], img.size[0]))
        dst.paste(img, (int(
            (i % grid_n)*osd_dims['mr']/grid_n), int(int(i/grid_n)*osd_dims['mr']/grid_n)))
    overlay1.update(
        dst, pos=(int(osd_dims['w'] - osd_dims['mr']), int(osd_dims['mt'])))


def render_selection():
    osd_dims = player.osd_dimensions
    width = int(osd_dims['mr']/grid_n)
    height = int(osd_dims['mr']/grid_n)
    dst = Image.new('RGBA', (width, height))
    draw = ImageDraw.Draw(dst)
    (i, color, _) = categories[segment_categories[current_segment()]]
    draw.rectangle([(0, 0), (width-1, height-1)],
                   width=width//10, outline=color)

    overlay2.update(dst, pos=(int((osd_dims['w'] - osd_dims['mr'])+(
        (i % grid_n)*osd_dims['mr']/grid_n)), int(int(i/grid_n)*osd_dims['mr']/grid_n)))


def render_bottom():
    osd_dims = player.osd_dimensions
    width = osd_dims['w'] - osd_dims['mr']
    dst = Image.new(
        'RGBA', (int(width), int(osd_dims['mb'])))

    draw = ImageDraw.Draw(dst)
    (_, color0, _) = categories[segment_categories[0]]
    if len(cuts) == 0:
        draw.rectangle([(0, 0), (width, int(osd_dims['mb']))],
                       width=0, fill=color0)
    else:
        draw.polygon([(0, 0),
                      (int((timeline_distortion*width *
                            cuts[0]/100) - (width*player.percent_pos/100)*(timeline_distortion-1)), 0),
                      (int(width*cuts[0]/100), int(osd_dims['mb'])),
                      (0, int(osd_dims['mb']))],
                     fill=color0)

        for i, (m1, m2) in enumerate(zip(cuts, cuts[1:]), 1):
            (_, colori, _) = categories[segment_categories[i]]
            x1 = width*m1/100
            x2 = width*m2/100
            draw.polygon([(int(timeline_distortion*x1 - (width*player.percent_pos/100)*(timeline_distortion-1)), 0),
                          (int(timeline_distortion*x2 - (width *
                                                    player.percent_pos/100)*(timeline_distortion-1)), 0),
                          (int(x2), int(osd_dims['mb'])),
                          (int(x1), int(osd_dims['mb']))],
                         fill=colori)
        (_, colorlast, _) = categories[segment_categories[-1]]

        draw.polygon([(int(timeline_distortion*width*cuts[-1]/100 - (width*player.percent_pos/100)*(timeline_distortion-1)), 0),
                      (int(timeline_distortion*width -
                           (width*player.percent_pos/100)*(timeline_distortion-1)), 0),
                      (int(width), int(osd_dims['mb'])),
                      (int(width*cuts[-1]/100), int(osd_dims['mb']))],
                     fill=colorlast)

        for m in cuts:
            x = m/100
            draw.line([(int(width*(timeline_distortion*x - (player.percent_pos/100)*(timeline_distortion-1))),
                        0), (int(width*x), int(osd_dims['mb']))])

    x = int(width*player.percent_pos/100)
    draw.line([(x, 0), (x, int(osd_dims['mb']))], fill=(255, 130, 20, 128))
    overlay4.update(dst, pos=(0, int(osd_dims['h'] - osd_dims['mb'])))


def current_segment():
    return bisect.bisect(cuts, player.percent_pos)


def save_state():
    if current_file != None:
        if not os.path.exists(annotations_path):
            os.makedirs(annotations_path)
        with open(join(annotations_path, current_file + '.annotations'), 'w') as f:
            data = {}
            data['cuts'] = cuts
            data['categories'] = segment_categories
            json.dump(data, f)


@ player.property_observer('osd-dimensions')
def osd_dimensions_observer(_name, value):
    render_grid()
    render_selection()
    render_bottom()


# We might not want to have this as a callback, just check it a lot.
@ player.property_observer('percent-pos')
def percent_pos_observer(_name, value):
    render_bottom()
    render_selection()


@ player.property_observer('filename')
def path_observer(_name, value):
    global current_file
    global cuts
    global segment_categories

    save_state()
    current_file = value

    if os.path.exists(annotations_path):
        with open(join(annotations_path, current_file + '.annotations'), 'r') as f:
            data = json.load(f)
            cuts = data['cuts']
            segment_categories = data['categories']
    else:
        cuts = []
        segment_categories = [None]


@ player.on_key_press('MOUSE_BTN0')
def mouse_btn0_observer():
    # HACK
    stream = os.popen(
        'xdotool search --name %s getwindowgeometry' % player.filename)
    output1 = stream.read().split(' ')[4].split(',')
    stream = os.popen('xdotool getmouselocation')
    output2 = stream.read().split(' ')
    x = int(output2[0][2:]) - int(output1[0])
    if player.fullscreen:
        y = int(output2[1][2:]) - int(output1[1])
    else:
        y = int(output2[1][2:]) - int(output1[1]) + 45

    osd_dims = player.osd_dimensions

    if osd_dims['w'] - osd_dims['mr'] < x and osd_dims['mt'] < y:
        xx = (x - (osd_dims['w'] - osd_dims['mr'])) / (osd_dims['mr']/grid_n)
        yy = y / (osd_dims['mr']/grid_n)
        i = grid_n*int(yy) + int(xx)
        if i < len(categories):
            global segment_categories
            segment_categories[current_segment()] = list(categories)[i]
            render_selection()
            render_bottom()
    elif x < osd_dims['w'] - osd_dims['mr'] and osd_dims['h'] - osd_dims['mb'] < y:
        width = osd_dims['w'] - osd_dims['mr']
        height = osd_dims['mb']

        blend_factor = (y - (osd_dims['h'] - osd_dims['mb']))/height
        top = 100*((x/width + (player.percent_pos/100) *
                    (timeline_distortion - 1))/(timeline_distortion))
        bottom = 100*x/width
        blend = (blend_factor*bottom + (1-blend_factor)*top)
        player.seek(blend, reference='absolute-percent', precision='exact')


@ player.on_key_press('s')
def s_observer():
    i = current_segment()
    cuts.insert(i, player.percent_pos)
    segment_categories.insert(i, segment_categories[i])
    render_bottom()


@ player.on_key_press('d')
def d_observer():
    if len(cuts) != 0:
        i = current_segment()
        if i != len(cuts):
            cuts.pop(i)
            segment_categories.pop(i)
            render_bottom()
            render_selection()


@ player.on_key_press('a')
def a_observer():
    if len(cuts) != 0:
        i = current_segment()
        if i != 0:
            cuts.pop(i-1)
            segment_categories.pop(i-1)
            render_bottom()
            render_selection()


@ player.on_key_press('ctrl+s')
def save_observer():
    print('saved')
    save_state()


while True:
    try:
        player.wait_for_playback()
    except mpv.ShutdownError:
        break
