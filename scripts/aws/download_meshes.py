#!/usr/bin/env python3
# Copyright 2004-present Facebook. All Rights Reserved.

# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

"""Downloads binary tar files from S3 and unpacks them locally.

Takes paths that corresponds to credentials for the user's AWS account,
S3 source and local destination paths and downloads and unpacks the tar files

Example:
        $ python sync_dir.py \
          --csv_path=/path/to/credentials.csv \
          --s3_dir=s3://path/to/src/ \
          --local_dir=/path/to/dst/

Attributes:
    FLAGS (absl.flags._flagvalues.FlagValues): Globally defined flags for clean.py.
"""

import glob
import os
import sys
import tarfile

from absl import app, flags
from watchdog.events import FileSystemEventHandler, FileMovedEvent
from watchdog.observers import Observer

dir_scripts = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
dir_root = os.path.dirname(dir_scripts)
sys.path.append(dir_root)
sys.path.append(os.path.join(dir_scripts, "render"))
sys.path.append(os.path.join(dir_scripts, "util"))

import glog_check as glog
from util import AWSUtil

FLAGS = flags.FLAGS


class ViewerHandler(FileSystemEventHandler):

    """Handles events triggered for extracting tar files as soon as we receive them.

    Attributes:
        local_dir (str): Path of the local directory to watch.
    """

    def on_moved(self, event):
        """When a tar file is created we unpack its contents and delete the file.

        Args:
            event (watchdog.FileSystemEvent): Watchdog event for when tar file is created.
        """
        if not isinstance(event, FileMovedEvent):
            return

        fn = event.dest_path
        if fn.endswith(".tar") and os.path.isfile(fn):
            extract_and_delete_tar(fn)


def extract_and_delete_tar(fn):
    print(f"Extracting {fn}...")
    tar = tarfile.open(fn)
    tar.extractall(path=os.path.dirname(fn))
    tar.close()
    os.remove(fn)


def main(argv):
    """Downloads binary tar files from S3 and unpacks them locally.

    Args:
        argv (list[str]): List of arguments (used interally by abseil).
    """
    os.makedirs(FLAGS.local_dir, exist_ok=True)

    if FLAGS.watch:
        event_handler = ViewerHandler()
        observer = Observer()
        observer.schedule(event_handler, path=FLAGS.local_dir, recursive=False)
        observer.start()

    # Download tar files
    glog.check(FLAGS.s3_dir.startswith("s3://"), "S3 directory must start with s3://")
    aws_util = AWSUtil(FLAGS.csv_path)

    try:
        print("Syncing files from S3...")
        aws_util.s3_sync(
            FLAGS.s3_dir,
            FLAGS.local_dir,
            exclude="*",
            include=["*.tar", "*.json"],
            run_silently=not FLAGS.verbose,
        )
    except KeyboardInterrupt:
        if FLAGS.watch:
            observer.stop()

    if FLAGS.watch:
        observer.stop()
        observer.join()

    # One last pass for missed files
    tars = list(glob.iglob(f"{FLAGS.local_dir}/*.tar", recursive=False))
    for fn in tars:
        extract_and_delete_tar(fn)


if __name__ == "__main__":
    # Abseil entry point app.run() expects all flags to be already defined
    flags.DEFINE_string("csv_path", None, "path to AWS credentials CSV")
    flags.DEFINE_string("local_dir", None, "path to local directory to sync to")
    flags.DEFINE_string("s3_dir", None, "path to S3 bin directory (starts with s3://)")
    flags.DEFINE_boolean("verbose", False, "Verbose mode")
    flags.DEFINE_boolean("watch", False, "Watch for files and extract as they appear")

    # Required FLAGS.
    flags.mark_flag_as_required("csv_path")
    flags.mark_flag_as_required("s3_dir")
    flags.mark_flag_as_required("local_dir")
    app.run(main)
