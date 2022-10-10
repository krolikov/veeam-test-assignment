"""
Performs one-way sync of two directories contents once in a given interval.
Produced as a test task for Veeam Software job application.
"""

import pathlib
import hashlib
import shutil
import logging
import argparse
import sched
import time
from logging.handlers import RotatingFileHandler
from os import mkfifo

def init_logger(log_file):
    """
    Instantiates a logger that will use a give file name as a log file and will mirror
    all output to stderr. Output to file uses RotatingFileHandler because log file
    rotation is required for a continuosly running script. By default logger is limited
    to 3 files of ~10MB.
    Logger level is set to INFO, so all INFO messages are logged by default.
    """

    log_format = logging.Formatter("%(asctime)s\t[%(levelname)-4.8s] %(message)s")
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    log_file_hnd = RotatingFileHandler(log_file, mode='a', maxBytes=10*1024*1024, backupCount=3)
    log_file_hnd.setFormatter(log_format)
    logger.addHandler(log_file_hnd)

    log_stderr_hnd = logging.StreamHandler()
    log_stderr_hnd.setFormatter(log_format)
    logger.addHandler(log_stderr_hnd)

    return logger

log = logging.getLogger()

def get_md5(filename):
    """
    Reads a given file in 4096 byte chunks (to limit memory usage when working
    with large files) and uses hashlib.md5 to calculate MD5 hash of a given file.
    Will return 0 instead of MD5 hash if any error occurs during the attempt
    to read the file and calculate hash (e.g. file is removed before reading is done)
    """
    try:
        with open(filename, 'rb') as file:
            file_md5 = hashlib.md5()
            chunk = file.read(4096)
            while chunk:
                file_md5.update(chunk)
                chunk = file.read(4096)
            return file_md5.hexdigest()
    except Exception as e:
        log.warning(f'Cannot get MD5 for {filename}, reason: {e}')
        return 0

def get_relative_path (rootpath, abspath):
    return pathlib.PurePath(abspath).relative_to(rootpath)

def get_absolute_path(rootpath, relpath):
    return pathlib.PurePath(rootpath).joinpath(relpath)

def get_files_in_path(scan_path):
    """
    Builds a dictionary object containing relative paths of files
    and directories in a given folders as keys. Values will contain
    MD5 hashes for files, and None for directories and named pipes.
    Ignores everything that is not a file, directory or a named pipe.
    """
    scanned_dir = dict()
    path = pathlib.Path(scan_path)
    for file in path.glob('**/*'):
        if pathlib.Path.is_file(file):
            file_md5 = get_md5(file)
        elif pathlib.Path.is_dir(file) or pathlib.Path.is_fifo(file):
            file_md5 = None
        else:
            # ignore special files: devices etc
            # to avoid issues while reading
            continue 
        file_relative = get_relative_path(scan_path, file)
        scanned_dir[file_relative] = file_md5
    return scanned_dir

def copy_verify_file(source_file, target_file):
    """
    Copies a file from source_file to target file, then verifies if MD5
    hashes are equal. If not, logs a warning (This is a basic way to keep 
    track of files not copied during the synchronization process.)
    """   
    # shutil.copy2 is used to preserve file attributes when copying
    shutil.copy2(source_file, target_file)
    hashes_equal = (get_md5(source_file) == get_md5(target_file))
    if not hashes_equal:
        log.warning(f'{source_file} modified during copying. MD5 hashes are different.')
    return hashes_equal

def copy_objects(source_files, target_files, source_path, target_path):
    """
    Takes two lists of relative paths, builds absolute paths from them, creates 
    directories and copies each file that is absent from target folder,
    of if MD5 hashes are different. Copying preserves attributes and ACL. Keeps 
    track of amount of objects created. Named pipes are created anew.
    Will log ERROR level messages in case of FileNotFount or PermissionError
    exceptions and continue working, copying whatever can still be copied.
    """
    total = 0
    for file, md5 in source_files.items():
        if file not in target_files.keys() or (md5 is not None and md5 not in target_files.values()):
            source_file = get_absolute_path(source_path, file)
            target_file = get_absolute_path(target_path, file)
            if pathlib.Path(source_file).is_dir():
                # if a source object is a directory, create a target directory
                # then copy attributes from source to target
                try:
                    pathlib.Path(target_file).mkdir(parents = True, exist_ok = True)
                    shutil.copystat(source_file, target_file)
                    total += 1
                    log.info(f'Created new directory: {target_file}')
                except PermissionError:
                    log.error(f'Cannot create directory {target_file}, insufficient permissions')
            elif pathlib.Path(source_file).is_fifo():
                try:
                    # have to use os.mkfifo because pathlib does not provide
                    # any means to create a fifo object
                    mkfifo(target_file)
                    shutil.copystat(source_file, target_file)
                    total += 1
                    log.info(f'Created new named pipe: {target_file}')
                except FileExistsError:
                    log.info(f'Named pipe {target_file} already exists, skipping...')
            else:
                # if not a directory or a named pipe, assume it's a file
                # copy file and verify hashes, log a warning if hashes don't match
                try:
                    copy_verify_file(source_file, target_file)
                    total += 1
                    log.info(f'Copied file, source: {source_file}, target: {target_file}')
                except FileNotFoundError:
                    log.error(f'Cannot copy {source_file}, file not found.')
                except PermissionError:
                    log.error(f'Cannot copy {source_file}, insufficient permissions')

    log.info(f'Total new objects: {total}')

def remove_objects(source_files, target_files, target_path):
    """
    Removes files and directories in target path if these objects are
    not in the source directory at the time of synchronization.
    Directories are removed after the files to avoid errors.
    Will log ERROR level messages in case of FileNotFound or
    PermissionError exceptions and continue working,
    removing whatever can still be removed.
    """
    dirs_to_remove = []
    total = 0

    for file in target_files.keys():
        if file not in source_files.keys():
            target_file = get_absolute_path(target_path, file)
            if pathlib.Path(target_file).is_dir():
                dirs_to_remove.append(target_file)
            else:
                try:
                    pathlib.Path(target_file).unlink()
                    total += 1
                    log.info(f'Removed file: {target_file}')
                except FileNotFoundError:
                    log.error(f'Cannot remove {target_file}, file not found.')
                except PermissionError:
                    log.error(f'Cannot remove {target_file}, insufficient permissions')

    for path in dirs_to_remove:
        try:
            pathlib.Path(path).rmdir()
            total += 1
            log.info(f'Removing empty directory: {path}')
        except FileNotFoundError:
            log.error(f'Cannot remove {path}, directory not found.')
        except PermissionError:
            log.error(f'Cannot remove {path}, insufficient permissions')

    log.info(f'Total removed objects: {total}')

def argument_parser():
    """
    Gets command line arguments. Source and target folder paths are required arguments. 
    Interval argument is optional, set to 60 seconds if not provided.
    Logfile is optional, set to dirsync.log if not provided.
    """
    argparser = argparse.ArgumentParser()
    argparser.add_argument('source', type=str,
                            help='Source folder for synchronization. Required argument')
    argparser.add_argument('target', type=str,
                            help='Target folder for synchronization. Required argument')
    argparser.add_argument('-o', '--oneshot', action='store_true', 
                            help='Run script in one shot mode, allowing to use external schedulers')
    argparser.add_argument('-i', '--interval', type=int, default=60*10,
                            help='Synchronization interval in seconds. Defaults to 600 seconds')
    argparser.add_argument('-l', '--logfile', type=str, nargs='?', default='dirsync.log',
                            help='Log file path. Defaults to dirsync.log')

    return argparser.parse_args()

def do_sync_dirs(source_path, target_path, schedule, interval):
    """
    Performs actual synchronization of source and target folders.
    Builds listings of source and target folders. Listings contain
    MD5 hashes for files that are then used to determine if a file 
    was modified. Then copies new and modified objects. 
    After copying scans for 'orphaned' files in target folder and removes them. 
    Returns a sched event, effectively scheduling this function to run every
    N seconds as controlled by interval parameter.
    """
    log.info('Scanning source folder...')
    source_files = get_files_in_path(source_path)
    log.info('Scanning target folder...')
    target_files = get_files_in_path(target_path)

    log.info('Comparing folders: Looking for files and directories to copy...')
    copy_objects(source_files, target_files, source_path, target_path)

    log.info('Comparing folders: Looking for files and directories to remove...')
    remove_objects(source_files, target_files, target_path)
    log.info('Done!')
    return schedule.enter(
                    interval,
                    1,
                    do_sync_dirs,
                    (source_path, target_path, schedule, interval)
                    )

def main():
    """
    Main function. Reads command line arguments, initializes logging system.
    Checks if source and target paths actually exist since running the 
    script with invalid paths is impossible.
    Creates a scheduler and calls do_sync_dirs that will return an event,
    that will run on schedule every N seconds.
    """
    args = argument_parser()
    log = init_logger(args.logfile)
    log.info('======== Startup ========')
    log.info('Logger initialized.')

    log.info(f'Using log file {args.logfile}')

    if args.oneshot:
        log.info('Running in one shot mode.')
    else:
        log.info(f'Sync interval set to {args.interval}')

    source_path = pathlib.Path(args.source).resolve()
    log.info(f'Source path set: {source_path}')
    target_path = pathlib.Path(args.target).resolve()
    log.info(f'Target path set: {target_path}')

    for path in [source_path, target_path]:
        if not path.exists():
            log.critical(f'{path} not found, exiting...')
            exit(1)

    schedule = sched.scheduler(time.time, time.sleep)

    try:
        do_sync_dirs(source_path, target_path, schedule, args.interval)
        
        # disable scheduler if one shot mode is enabled
        if not args.oneshot:
            schedule.run()
    except KeyboardInterrupt:
        log.info('Shutting down on keyboard interrupt...')
        exit(0)

if __name__ == '__main__':
    main()
