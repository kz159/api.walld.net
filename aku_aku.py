'''This code fills db that api is looking for, providing with urls and
other stuff, kindly and jently.'''
#For now (1.10.19) it can only write things like file name, category.
#sub_category, height, weight, dominated color and url
#Need to add pillow maybe? DONE

#must run by cron every day to update db with wallpapers that sits in folders

import os
import multiprocessing
from time import sleep
import argparse
import colorgram
import requests
from PIL import Image
import sql_worker
import config

PARSER = argparse.ArgumentParser()
PARSER.add_argument('-c', type=int, help='how many to calculate')
PARSER.add_argument('-n', type=int, help='how many to calculate without threading')
ARGS = PARSER.parse_args()

MANAGER = multiprocessing.Manager()
color_staff = MANAGER.dict()

try:
    os.makedirs(config.SEARCH_DIR)
except FileExistsError:
    pass

sql_boy = sql_worker.SqlBoy(db_type=config.DB)

def list_dir(directory):
    '''returns generated list with folders'''
    subfolders = [f.name for f in os.scandir(directory) if f.is_dir()]
    return subfolders

def get_id():
    '''gets id based on existing maximun, returns -1 if didn`t find anything'''
    result = sql_boy.execute('SELECT MAX(id) FROM pics DESC LIMIT 1', fetch='one')
    if not result:
        return -1
    return result[0]

def sync_add():
    '''recursivly walks on given folder and adds it
    to db using folder name as category'''
    idd = get_id()+1
    print(idd)
    for category in list_dir(config.SEARCH_DIR):
        print('entering  category:' + category)

        for sub_category in list_dir(config.SEARCH_DIR + category):
            print('-'*30 + '>' + sub_category + '<' + '-'*30)

            for filename in os.listdir(config.SEARCH_DIR +
                                       category + '/'+
                                       sub_category):
                full_path = config.SEARCH_DIR + category + \
                            '/' + sub_category + '/' + filename
                if ' ' in full_path:
                    os.rename(full_path, full_path.replace(' ', '_'))
                    full_path = full_path.replace(' ', '_')
                sql = sql_boy.gen_line("SELECT file_name FROM pics WHERE file_name={0}")
                found_row = sql_boy.execute(sql, args=(filename,), fetch='one')
                if not found_row:
                    print(filename, 'is new here')
                    with Image.open(full_path) as img:
                        width, height = img.size
                    command = (idd, category, sub_category, filename,
                               width, height, 'ratio_here', 'no_color',
                               config.PART_OF_URL + category + '/' + \
                               sub_category + '/' + filename.replace(' ', '_'), '0')
                    line = sql_boy.gen_line("INSERT INTO pics VALUES ({0}, {0}, {0},\
                                             {0}, {0}, {0}, {0}, {0}, {0}, {0})")
                    sql_boy.execute(line, command)
                    idd += 1

def sync_del():
    '''This section emplements deleting non existing file.
    if file was deleted for some reason, than we need to update our db'''
    print('*'*33, 'DELETE', '*'*32)
    sql_line = sql_boy.gen_line("SELECT * FROM pics WHERE url LIKE {0} ESCAPE ''")
    list_of_boys = sql_boy.execute(sql_line, args=(config.PART_OF_URL,), fetch='all')
    try:
        for row in list_of_boys:
            file_path = config.SEARCH_DIR + row['category'] + \
            '/' + row['sub_category'] + '/' + row['file_name']
            if not os.path.exists(file_path):
                print('deleting', file_path, 'from sql base')
                sql = sql_boy.gen_line("DELETE FROM pics WHERE file_name = {0}")
                sql_boy.execute(sql, args=(row['file_name'],))
    except TypeError:
        print('nothing to delete')
            # if we attempt to delete something on cursor
            # then whole row will vanish

def get_dom_color(img, hex_type=True):# maybe we need some rewrite to return tuple of em?
    '''gets dominant color'''
    colors = colorgram.extract(img, 1)
    print(colors)
    if hex_type:
        return '#%02x%02x%02x' % colors[0].rgb
    return colors[0].rgb

def calc_colors(row):
    '''gives get_dom_color function args and writes output to dict'''
    request = requests.get(row['url'])
    file_path = config.TEMP_FOLDER + row['file_name']
    if request.status_code == 200:
        open(file_path, 'wb').write(request.content)
        color = get_dom_color(file_path)
        color_staff[str(row['id'])] = color
        os.remove(file_path)
    else:
        print('some kind of error, need to check', row)

def main():
    '''main boy'''
    procs = []
    alive = True
    ids = []
    sync_add()
    sync_del()
    sql_boy.commit()
    row_list = sql_boy.execute("SELECT * FROM pics WHERE color = 'no_color'\
                                AND locked = '0'", fetch='all')
    sql = sql_boy.gen_line("UPDATE pics SET color = {0} WHERE id = {0}")

    if ARGS.c:
        for _ in range(ARGS.c):
            row = row_list.pop(0)
            if row:
                sql_boy.execute(sql_boy.gen_line("UPDATE pics SET locked = '1'\
                                                  WHERE id = {0}"), (row['id'], ))
                ids.append(row['id'])
                thread = multiprocessing.Process(target=calc_colors,
                                                 args=(row,))
                procs.append(thread)
                thread.start()
        print('aha')
        sql_boy.commit()
        while alive:
            get = []
            for i in procs:
                get.append(i.is_alive())
            if not any(get):
                alive = False
                if color_staff:
                    print(color_staff)
                else:
                    print('nothing to calc!')
            sleep(1)

    elif ARGS.n:
        for _ in range(ARGS.n):
            row = row_list(0)
            sql_boy.execute(sql_boy.gen_line("UPDATE pics SET locked = '1' WHERE id = {0}"), (i, ))
            sql_boy.commit()
            calc_colors(row)
            ids.append(row['id'])

    for i in ids:
        sql_boy.execute(sql_boy.gen_line("UPDATE pics SET locked = '0' WHERE id = {0}"), (i, ))
    for key in color_staff:
        sql_boy.execute(sql, (color_staff[key], key))

    sql_boy.commit()
    sql_boy.close_connection()
main()
