# DirSync
> Performs one-way sync of two directories contents once in a given interval.
> Produced as a test task for Veeam Software job application.

## Features
- Takes source and target paths as command line arguments (both required). 
- Logs all activity to stderr and a log file (default: dirsync.log, can be modified via [-l, --logfile] argument).
- Runs every 60 seconds (interval can be changed via [-i, --interval] argument)
- Supports synchronization of files, directories and named pipes. Preserves attributes.

## Usage
```
usage: dirsync.py [-h] [-o] [-i INTERVAL] [-l [LOGFILE]] source target

positional arguments:
  source                Source folder for synchronization. Required argument
  target                Target folder for synchronization. Required argument

optional arguments:
  -h, --help            show this help message and exit
  -o, --oneshot         Run script in one shot mode, allowing to use external schedulers
  -i INTERVAL, --interval INTERVAL
                        Synchronization interval in seconds. Defaults to 600 seconds
  -l [LOGFILE], --logfile [LOGFILE]
                        Log file path. Defaults to dirsync.log
```

## Tests
test_dirsync.py file contains unit test covering script functions, implemented using unittest Python module.

## Additional comments
Reasoning for some decisions is described in docstrings within the script. I am not publishing the original task description, however here are some comments regarding the task description and my implementation:

1. The original description did not state whether or not network locations would be involved in the synchronization process, so the script works with assumption that all network folders are already mounted and authorization is done outside of the script.

2. Re: "content of the replica folder should be modified to exactly match content of the source folder" - no requirements provided regarding a situation when an error occurs (e.g. file not found, not enough privilege etc) - currently if any error leads to a file not being copied or removed, the replica folder will not be identical to the source. One can implement automatic verification of the two folders with automatic retries, or one can interactively ask for user input, but since nothing was specified in the description, I did not implement any of this. Script logs a warning if MD5 hashes are different after copying, thus informing of any inconsistencies in a synchronization run.

3. To ensure that we copy the latest available version of a file one could check if a file is being written to at the time of copying (e.g. if a file is locked by another process). This could be handled by implementing multithreaded copying (copy each file in a separate thread, make thread wait until lock is released), but since this was not a part of the original task description and also bears a risk of having a thread indefinitely waiting for another process thus blocking the otherwise successful synchronization run and messing with scheduling, I decided against implementing it. Script will copy whatever file is currently stored on disk and any ongoing modifications will be synchronized in the next synchronization run.

4. The current implementation works with files, directories and named pipes but ignores any other file-like objects (devices etc.) to avoid reading issues. This imitates behavior of established file managers like Nautilus (will display an error when trying to copy a named pipe).

5. For convenience sake f-strings are used throughout the script to build log messages, although performance-wise it would be better to use lazy % formatting. 
