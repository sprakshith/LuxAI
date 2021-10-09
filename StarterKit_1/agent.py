import math, sys, random
import logging

from lux.game import Game
from lux.game_map import Cell, RESOURCE_TYPES, Position
from lux.constants import Constants
from lux.game_constants import GAME_CONSTANTS
from lux import annotate
from collections import Counter, deque
from tracker import UnitTracker

import json

DIRECTIONS = Constants.DIRECTIONS
game_state = None

unit_pos_dict = {}
occupied_tiles = {}
reserved_tiles = {}
unit_tracker_dict = {}

build_citytiles_initiated = 0
build_workers_initiated = 0

open("LOGS/log_agent.txt", 'w').write("")

logging.basicConfig(filename="LOGS/log_agent.txt",
                    filemode='a',
                    format='%(levelname)s at line No. %(lineno)d: %(message)s',
                    datefmt='%H:%M:%S',
                    level=logging.INFO)


def get_resource_tiles(width, height):
    global game_state

    resource_tiles: list[Cell] = []

    for y in range(height):
        for x in range(width):
            cell = game_state.map.get_cell(x, y)
            if cell.has_resource():
                resource_tiles.append(cell)

    return resource_tiles


def get_empty_tiles(width, height):
    global game_state

    empty_tiles: list[Cell] = []

    for y in range(height):
        for x in range(width):
            cell = game_state.map.get_cell(x, y)
            if cell.resource or cell.citytile:
                pass
            else:
                empty_tiles.append(cell)

    return empty_tiles


def get_closest_resource_tile(resource_tiles, unit, player):
    closest_dist = math.inf
    closest_resource_tile = None
    for resource_tile in resource_tiles:
        if resource_tile.resource.type == Constants.RESOURCE_TYPES.COAL and not player.researched_coal():
            continue
        if resource_tile.resource.type == Constants.RESOURCE_TYPES.URANIUM and not player.researched_uranium():
            continue

        dist = resource_tile.pos.distance_to(unit.pos)

        if dist < closest_dist:
            resource_tile_pos = (resource_tile.pos.x, resource_tile.pos.y)
            if resource_tile_pos not in get_restricted_tiles():
                closest_dist = dist
                closest_resource_tile = resource_tile

    # if closest_resource_tile is not None:
    #     update_occupied_tiles(unit, closest_resource_tile, closest_dist)

    return closest_resource_tile


def get_closest_empty_tile(empty_tiles, unit):
    closest_dist = math.inf
    closest_empty_tile = None
    for empty_tile in empty_tiles:
        dist = empty_tile.pos.distance_to(unit.pos)
        if dist < closest_dist:
            empty_tile_pos = (empty_tile.pos.x, empty_tile.pos.y)
            if empty_tile_pos not in get_restricted_tiles():
                closest_dist = dist
                closest_empty_tile = empty_tile

    # if closest_empty_tile is not None:
    #     update_occupied_tiles(unit, closest_empty_tile, closest_dist)

    return closest_empty_tile


def get_closest_city_tile(unit, player):
    closest_city_tile = None
    if len(player.cities) > 0:
        closest_dist = math.inf
        for k, city in player.cities.items():
            for city_tile in city.citytiles:
                dist = city_tile.pos.distance_to(unit.pos)
                if dist < closest_dist:
                    closest_dist = dist
                    closest_city_tile = city_tile

    return closest_city_tile


def should_we_build_a_citytile(player, unit):
    global build_citytiles_initiated
    global build_workers_initiated

    citytiles_count = get_total_city_tiles(player) + build_citytiles_initiated
    total_workers = get_total_units(player) + build_workers_initiated

    enough_resource = unit.cargo.wood == 100 or unit.cargo.coal == 100 or unit.cargo.uranium == 100

    if citytiles_count == 0:
        return True and enough_resource
    else:
        ratio = total_workers / citytiles_count
        if ratio > 0.8:
            return True and enough_resource

    return False


def should_we_create_a_worker(player):
    global build_citytiles_initiated
    global build_workers_initiated

    citytiles_count = get_total_city_tiles(player) + build_citytiles_initiated
    total_workers = get_total_units(player) + build_workers_initiated

    if citytiles_count != 0:
        ratio = total_workers / citytiles_count
        if ratio <= 0.8:
            return True

    return False


def create_unit_type(player):
    global build_workers_initiated

    cart_count = len([unit for unit in player.units if unit.is_cart()])
    worker_count = len([unit for unit in player.units if unit.is_worker()])

    logging.info(f"{int(worker_count/5)} < {cart_count}")
    if cart_count < int(worker_count/5):
        return "Cart"

    return "Worker"


def get_total_city_tiles(player):
    total_city_tile = 0

    for k, city in player.cities.items():
        total_city_tile += len(city.citytiles)

    return total_city_tile


def get_total_units(player):
    total_units = len(player.units)
    return total_units


def collect_resource(unit, closest_resource_tile, actions):
    global reserved_tiles
    global unit_tracker_dict

    # Updating Units Destination
    unit_tracker = unit_tracker_dict[unit.id]
    unit_tracker.destination = (closest_resource_tile.pos.x, closest_resource_tile.pos.y)

    # Updating Occupied Tiles Dictionary
    reserved_tiles[unit.id] = (closest_resource_tile.pos.x, closest_resource_tile.pos.y)

    move_dir = unit.pos.direction_to(closest_resource_tile.pos)
    actions.append(unit.move(move_dir))

    return actions


def transfer_resource_to_citytile(unit, closest_city_tile, actions):
    global unit_tracker_dict

    # Updating Units Destination
    unit_tracker = unit_tracker_dict[unit.id]
    unit_tracker.destination = (closest_city_tile.pos.x, closest_city_tile.pos.y)

    move_dir = unit.pos.direction_to(closest_city_tile.pos)
    actions.append(unit.move(move_dir))

    return actions


def move_unit_to_empty_tile(closest_empty_tile, unit, actions):
    global occupied_tiles
    global unit_tracker_dict

    # Updating Units Destination
    unit_tracker = unit_tracker_dict[unit.id]
    unit_tracker.destination = (closest_empty_tile.pos.x, closest_empty_tile.pos.y)

    move_dir = unit.pos.direction_to(closest_empty_tile.pos)
    actions.append(unit.move(move_dir))

    return actions


def move_unit_in_random_direction(unit, actions, width, height):
    global reserved_tiles

    direction_list = ["n", "s", "e", "w"]
    direction = random.choice(direction_list)

    unit_next_x_pos = unit.pos.x + get_x_pos(direction)
    unit_next_y_pos = unit.pos.y + get_y_pos(direction)
    unit_next_pos = (unit_next_x_pos, unit_next_y_pos)

    if 0 <= unit_next_x_pos < width and 0 <= unit_next_y_pos < height:
        reserved_tiles[unit.id] = (unit_next_x_pos, unit_next_y_pos)
        actions.append(unit.move(direction))
        return actions

    return move_unit_in_random_direction(unit, actions, width, height)


def get_x_pos(direction):
    if direction == 'e':
        return 1
    elif direction == 'w':
        return -1
    else:
        return 0


def get_y_pos(direction):
    if direction == 's':
        return 1
    elif direction == 'n':
        return -1
    else:
        return 0


def update_unit_tracker_dict(units):
    global unit_tracker_dict

    uids = [u.id for u in units]

    # Remove the Dead Units
    dead_units = []

    for uid in unit_tracker_dict.keys():
        if uid not in uids:
            dead_units.append(uid)

    for uid in dead_units:
        unit_tracker_dict.pop(uid)

    # Creating UnitTracker
    for unit in units:
        if unit.id not in unit_tracker_dict.keys():
            unit_tracker_dict[unit.id] = UnitTracker(unit.id, 'c_1', None)
        else:
            unit_tracker = unit_tracker_dict[unit.id]
            unit_current_pos = (unit.pos.x, unit.pos.y)

            if unit_tracker.destination == unit_current_pos:
                unit_tracker.destination = None
                unit_tracker_dict[unit.id] = unit_tracker


def update_occupied_tiles(units):
    global occupied_tiles
    occupied_tiles ={}

    for unit in units:
        if not unit.can_act():
            occupied_tiles[unit.id] = (unit.pos.x, unit.pos.y)


def update_reserved_tiles(units):
    global unit_tracker_dict

    global reserved_tiles
    reserved_tiles = {}

    # Creating UnitTracker
    for unit in units:
        if unit.id in unit_tracker_dict.keys():
            unit_tracker = unit_tracker_dict[unit.id]
            destination = unit_tracker.destination

            if destination:
                reserved_tiles[unit.id] = destination


def get_restricted_tiles():
    global occupied_tiles
    global reserved_tiles

    occupied = list(occupied_tiles.values())
    reserved = list(reserved_tiles.values())

    return occupied + reserved


def agent(observation, configuration):
    global game_state

    ### Do not edit ###
    if observation["step"] == 0:
        game_state = Game()
        game_state._initialize(observation["updates"])
        game_state._update(observation["updates"][2:])
        game_state.id = observation.player
    else:
        game_state._update(observation["updates"])

    actions = []

    # GLOBAL VARIABLES
    global build_citytiles_initiated
    build_citytiles_initiated = 0

    global build_workers_initiated
    build_workers_initiated = 0

    global unit_pos_dict
    global unit_tracker_dict
    global occupied_tiles

    ### AI Code goes down here! ###
    player = game_state.players[observation.player]
    opponent = game_state.players[(observation.player + 1) % 2]
    width, height = game_state.map.width, game_state.map.height

    resource_tiles = get_resource_tiles(width, height)

    update_unit_tracker_dict(player.units)
    update_occupied_tiles(player.units)
    update_reserved_tiles(player.units)

    workers = [u for u in player.units if u.is_worker()]
    for w in workers:
        if w.id in unit_pos_dict:
            unit_pos_dict[w.id].append((w.pos.x, w.pos.y))
        else:
            unit_pos_dict[w.id] = deque(maxlen=4)
            unit_pos_dict[w.id].append((w.pos.x, w.pos.y))

    # we iterate over all our units and do something with them
    for unit in player.units:
        if unit.is_worker() and unit.can_act():

            # If a unit is stuck in a same position for 4 Turns, move the unit in random direction
            last_positions = unit_pos_dict[unit.id]
            if len(last_positions) == 4:
                hm_positions = set(last_positions)
                if len(list(hm_positions)) == 1:
                    actions = move_unit_in_random_direction(unit, actions, width, height)
                    continue

            if unit.id in unit_tracker_dict.keys():
                unit_tracker = unit_tracker_dict[unit.id]
                if unit_tracker.unit_has_work():
                    if unit.can_act():
                        position = Position(unit_tracker.destination[0], unit_tracker.destination[1])
                        move_dir = unit.pos.direction_to(position)
                        actions.append(unit.move(move_dir))
                    continue

            closest_city_tile = get_closest_city_tile(unit, player)

            if unit.get_cargo_space_left() > 0:
                closest_resource_tile = get_closest_resource_tile(resource_tiles, unit, player)
                if closest_resource_tile is not None:
                    actions = collect_resource(unit, closest_resource_tile, actions)
                elif closest_city_tile is not None:
                    actions = transfer_resource_to_citytile(unit, closest_city_tile, actions)
                else:
                    actions = move_unit_in_random_direction(unit, actions, width, height)
            else:
                build_citytile = should_we_build_a_citytile(player, unit)
                if build_citytile:
                    if unit.can_build(game_state.map):
                        actions.append(unit.build_city())
                        build_citytiles_initiated += 1
                    else:
                        empty_tiles = get_empty_tiles(width, height)
                        closest_empty_tile = get_closest_empty_tile(empty_tiles, unit)
                        if closest_empty_tile is not None:
                            actions = move_unit_to_empty_tile(closest_empty_tile, unit, actions)
                        else:
                            actions = move_unit_in_random_direction(unit, actions, width, height)
                elif closest_city_tile is not None:
                    actions = transfer_resource_to_citytile(unit, closest_city_tile, actions)
                else:
                    actions = move_unit_in_random_direction(unit, actions, width, height)
        elif unit.is_cart() and unit.can_act():
            if unit.get_cargo_space_left() > 0:
                closest_resource_tile = get_closest_resource_tile(resource_tiles, unit, player)
                if closest_resource_tile is not None:
                    actions = collect_resource(unit, closest_resource_tile, actions)
                elif closest_city_tile is not None:
                    actions = transfer_resource_to_citytile(unit, closest_city_tile, actions)
                else:
                    actions = move_unit_in_random_direction(unit, actions, width, height)
            else:
                actions = transfer_resource_to_citytile(unit, closest_city_tile, actions)
        else:
            pass

    # We Iterate over all our Citytile to Research or Create More Units
    for k, city in player.cities.items():
        for city_tile in city.citytiles:
            if city_tile.can_act():
                build_worker = should_we_create_a_worker(player)
                if build_worker:
                    worker_type = create_unit_type(player)

                    if worker_type == "Worker":
                        actions.append(city_tile.build_worker())
                    elif worker_type == "Cart":
                        actions.append(city_tile.build_cart())

                    build_workers_initiated += 1
                else:
                    actions.append(city_tile.research())

    if game_state.turn == 360:
        pass

    return actions
