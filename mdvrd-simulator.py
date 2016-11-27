#!/usr/bin/python3
# -*- coding: utf-8 -*-

import time
import sys
import os
import json
import datetime
import argparse
import pprint
import socket
import struct
import functools
import uuid
import random
import math
import addict
import cairo
import shutil
from PIL import Image



NO_ROUTER = 100

SIMULATION_TIME_SEC = 60 * 60

TX_INTERVAL = 30
TX_INTERVAL_JITTER = int(TX_INTERVAL / 4)

# two stiched images result in 1080p resoltion
SIMU_AREA_X = 960
SIMU_AREA_Y = 1080

random.seed(1)

class Router:

    class MobilityModel:

        LEFT = 1
        RIGHT = 2
        UPWARDS = 1
        DOWNWARDS = 2

        def __init__(self):
            self.direction_x = random.randint(0, 2)
            self.direction_y = random.randint(0, 2)
            self.velocity = random.randint(1, 1)

        def _move_x(self, x):
            if self.direction_x == Router.MobilityModel.LEFT:
                x -= self.velocity
                if x <= 0:
                    self.direction_x = Router.MobilityModel.RIGHT
                    x = 0
            elif self.direction_x == Router.MobilityModel.RIGHT:
                x += self.velocity
                if x >= SIMU_AREA_X:
                    self.direction_x = Router.MobilityModel.LEFT
                    x = SIMU_AREA_X
            else:
                pass
            return x

        def _move_y(self, y):
            if self.direction_y == Router.MobilityModel.DOWNWARDS:
                y += self.velocity
                if y >= SIMU_AREA_Y:
                    self.direction_y = Router.MobilityModel.UPWARDS
                    y = SIMU_AREA_Y
            elif self.direction_y == Router.MobilityModel.UPWARDS:
                y -= self.velocity
                if y <= 0:
                    self.direction_y = Router.MobilityModel.DOWNWARDS
                    y = 0
            else:
                pass
            return y

        def move(self, x, y):
            x = self._move_x(x)
            y = self._move_y(y)
            return x, y


    def __init__(self, id, ti, prefix):
        self.id = id
        self.ti = ti
        self.prefix = prefix
        self.pos_x = random.randint(0, SIMU_AREA_X)
        self.pos_y = random.randint(0, SIMU_AREA_Y)
        self.time = 0
        self._init_terminals
        self.terminals = addict.Dict()
        self._calc_next_tx_time()
        self.mm = Router.MobilityModel()
        self.route_rx_data = dict()
        self.transmitted_now = False


    def _calc_next_tx_time(self):
            self._next_tx_time = self.time + TX_INTERVAL + random.randint(0, TX_INTERVAL_JITTER)


    def _init_terminals(self):
        for t in self.ti:
            self.terminals[t['path_type']] = addict.Dict()
            self.terminals[t['path_type']].connections = dict()

    def dist_update(self, dist, other):
        """connect is just information base on distance
           path loss or other effects are modeled afterwards.
           This models the PHY channel somehow."""
        for v in self.ti:
            t = v['path_type']
            max_range = v['range']
            if dist <= max_range:
                #print("{} in range:     {} to {} - {} m via {}".format(t, self.id, other.id, dist, t))
                self.terminals[t].connections[other.id] = other
            else:
                #print("{} out of range: {} to {} - {} m".format(t, self.id, other.id, dist))
                if other.id in self.terminals[t].connections:
                    del self.terminals[t].connections[other.id]

    def _rx_save_data(self, sender, packet):
        if not sender in self.route_rx_data:
            self.route_rx_data[sender] = dict()
            self.route_rx_data[sender][packet['path_type']] = dict()
            self.route_rx_data[sender][packet['path_type']]['rx-time'] = self.time

    def receive(self, sender, packet):
        print("{} receive packet from {}".format(self.id, sender.id))
        print("  path_type: {}\n".format(packet['path_type']))
        #pprint.pprint(packet)
        self._rx_save_data(sender, packet)

    def create_packet(self, path_type):
        packet = dict()
        packet['router-id'] = self.id
        packet['path_type'] = path_type
        packet['networks'] = list()
        packet['networks'].append({"v4-prefix" : self.prefix})
        return packet

    def _transmit(self):
        #print("{} transmit data".format(self.id))
        for v in self.ti:
            pt = v['path_type']
            for other_id, other_router in self.terminals[pt].connections.items():
                """ this is the multicast packet transmission process """
                #print(" to router {} [{}]".format(other_id, t))
                packet = self.create_packet(pt)
                other_router.receive(self, packet)


    def pos(self):
        return self.pos_x, self.pos_y

    def step(self):
        self.time += 1
        self.pos_x, self.pos_y = self.mm.move(self.pos_x, self.pos_y)
        if self.time == self._next_tx_time:
            self._transmit()
            self._calc_next_tx_time()
            self.transmitted_now = True
        else:
            self.transmitted_now = False


def rand_ip_prefix():
	addr = random.randint(0, 4000000000)
	a = socket.inet_ntoa(struct.pack("!I", addr))
	b = a.split(".")
	c = "{}.{}.{}.0/24".format(b[0], b[1], b[2])
	return c

def dist_update_all(r):
    for i in range(NO_ROUTER):
        for j in range(NO_ROUTER):
            if i == j: continue
            i_pos = r[i].pos()
            j_pos = r[j].pos()
            dist = math.hypot(i_pos[1] - j_pos[1], i_pos[0] - j_pos[0])
            r[j].dist_update(dist, r[i])


def draw_router_loc(r, path, img_idx):
    c_links = { 'nb' : (1.0, 0.15, 0.15, 1.0),  'wb' :(0.15, 1.0, 0.15, 1.0)}
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, SIMU_AREA_X, SIMU_AREA_Y)
    ctx = cairo.Context(surface)
    ctx.rectangle(0, 0, SIMU_AREA_X, SIMU_AREA_Y)
    ctx.set_source_rgba(0.15, 0.15, 0.15, 1.0) 
    ctx.fill()

    for i in range(NO_ROUTER):
        router = r[i]
        x = router.pos_x
        y = router.pos_y

        color = ((1.0, 1.0, 0.5, 0.05), (1.0, 0.0, 1.0, 0.05))
        ctx.set_line_width(0.1)
        path_thinkness = 4.0
        # iterate over links
        for i, t in enumerate(router.ti):
            range_ = t['range']
            path_type = t['path_type']
            ctx.set_source_rgba(*color[i])
            ctx.move_to(x, y)
            ctx.arc(x, y, range_, 0, 2 * math.pi)
            ctx.fill()

            # draw lines between links
            ctx.set_line_width(path_thinkness)
            for r_id, other in router.terminals[t['path_type']].connections.items():
                other_x, other_y = other.pos_x, other.pos_y
                ctx.move_to(x, y)
                ctx.set_source_rgba(*c_links[path_type])
                ctx.line_to(other_x, other_y)
                ctx.stroke()

            path_thinkness -= 2.0

    for i in range(NO_ROUTER):
        router = r[i]
        x = router.pos_x
        y = router.pos_y

        # node middle point
        ctx.set_line_width(0.0)
        ctx.set_source_rgb(0.5, 1, 0.5)
        ctx.move_to(x, y)
        ctx.arc(x, y, 5, 0, 2 * math.pi)
        ctx.fill()

        # router id
        ctx.set_font_size(10)
        ctx.set_source_rgb(0.5, 1, 0.7)
        ctx.move_to(x + 10, y + 10)
        ctx.show_text(str(router.id))

        # router IP prefix
        ctx.set_font_size(8)
        ctx.set_source_rgba(0.5, 1, 0.7, 0.5)
        ctx.move_to(x + 10, y + 20)
        ctx.show_text(router.prefix)

    full_path = os.path.join(path, "{0:05}.png".format(img_idx))
    surface.write_to_png(full_path)


def draw_router_transmission(r, path, img_idx):
    c_links = { 'nb' : (.0, .0, .0, .4),  'wb' :(.0, .0, .0, .4)}
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, SIMU_AREA_X, SIMU_AREA_Y)
    ctx = cairo.Context(surface)
    ctx.rectangle(0, 0, SIMU_AREA_X, SIMU_AREA_Y)
    ctx.set_source_rgba(0.15, 0.15, 0.15, 1.0) 
    ctx.fill()

    # transmitting circles
    for i in range(NO_ROUTER):
        router = r[i]
        x = router.pos_x
        y = router.pos_y

        if router.transmitted_now:
            ctx.set_source_rgba(.10, .10, .10, 1.0)
            ctx.move_to(x, y)
            ctx.arc(x, y, 50, 0, 2 * math.pi)
            ctx.fill()


    for i in range(NO_ROUTER):
        router = r[i]
        x = router.pos_x
        y = router.pos_y

        color = ((1.0, 1.0, 0.5, 0.05), (1.0, 0.0, 1.0, 0.05))
        ctx.set_line_width(0.1)
        path_thinkness = 4.0
        # iterate over links
        for i, t in enumerate(router.ti):
            range_ = t['range']
            path_type = t['path_type']

            # draw lines between links
            ctx.set_line_width(path_thinkness)
            for r_id, other in router.terminals[t['path_type']].connections.items():
                other_x, other_y = other.pos_x, other.pos_y
                ctx.move_to(x, y)
                ctx.set_source_rgba(*c_links[path_type])
                ctx.line_to(other_x, other_y)
                ctx.stroke()

            path_thinkness -= 2.0


    # draw dots over all
    for i in range(NO_ROUTER):
        router = r[i]
        x = router.pos_x
        y = router.pos_y

        ctx.set_line_width(0.0)
        ctx.set_source_rgb(0, 0, 0)
        ctx.move_to(x, y)
        ctx.arc(x, y, 5, 0, 2 * math.pi)
        ctx.fill()


    full_path = os.path.join(path, "{0:05}.png".format(img_idx))
    surface.write_to_png(full_path)

def image_merge(merge_path, range_path, tx_path, img_idx):

    m_path = os.path.join(merge_path, "{0:05}.png".format(img_idx))
    r_path = os.path.join(range_path, "{0:05}.png".format(img_idx))
    t_path = os.path.join(tx_path,    "{0:05}.png".format(img_idx))

    images = map(Image.open, [r_path, t_path])
    new_im = Image.new('RGB', (1920, 1080))

    x_offset = 0
    for im in images:
        new_im.paste(im, (x_offset,0))
        x_offset += im.size[0]

    new_im.save(m_path, "PNG")


PATH_IMAGES_RANGE = "images-range"
PATH_IMAGES_TX    = "images-tx"
PATH_IMAGES_MERGE = "images-merge"


def draw_images(r, img_idx):
    draw_router_loc(r, PATH_IMAGES_RANGE, img_idx)
    draw_router_transmission(r, PATH_IMAGES_TX, img_idx)

    image_merge(PATH_IMAGES_MERGE, PATH_IMAGES_RANGE, PATH_IMAGES_TX, img_idx)

def setup_img_folder():
    for path in (PATH_IMAGES_RANGE, PATH_IMAGES_TX, PATH_IMAGES_MERGE):
        if os.path.exists(path):
            shutil.rmtree(path)
        os.makedirs(path)

def main():
    setup_img_folder()

    ti = [ {"path_type": "wb", "range" : 100, "bandwidth" : 5000},
           {"path_type": "nb", "range" : 150, "bandwidth" : 1000 } ]

    r = dict()
    for i in range(NO_ROUTER):
        prefix = rand_ip_prefix()
        print(prefix)
        r[i] = Router(i, ti, prefix)

    # initial positioning
    dist_update_all(r)

    for sec in range(SIMULATION_TIME_SEC):
        print("time:{} of:{}".format(sec, SIMULATION_TIME_SEC))
        for i in range(NO_ROUTER):
            r[i].step()
        dist_update_all(r)
        draw_images(r, sec)

    cmd = "ffmpeg -framerate 10 -pattern_type glob -i 'images-merge/*.png' -c:v libx264 -pix_fmt yuv420p out.mp4"
    print("now execute \"{}\" to generate a video".format(cmd))


if __name__ == '__main__':
    main()
