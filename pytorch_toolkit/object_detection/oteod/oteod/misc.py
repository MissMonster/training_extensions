# pylint: disable=W0702,W1203,R0913

import json
import os
import signal
import subprocess
import sys
import time
from queue import Queue, Empty
from threading import Thread

from oteod import MMDETECTION_TOOLS


class NonBlockingStreamReader:

    def __init__(self, stream):
        self.stream = stream
        self.queue = Queue()

        def populate_queue(stream, queue):
            while True:
                line = stream.readline()
                if line:
                    queue.put(line)
                else:
                    time.sleep(1)

        self.thread = Thread(target=populate_queue, args=(self.stream, self.queue))
        self.thread.daemon = True
        self.thread.start()

    def readline(self, timeout=None):
        try:
            return self.queue.get(block=timeout is not None, timeout=timeout)
        except Empty:
            return None


def get_complexity_and_size(cfg, config_path, work_dir, update_config):
    """ Gets complexity and size of a model. """

    image_shape = [x['img_scale'] for x in cfg.test_pipeline if 'img_scale' in x][0][::-1]
    image_shape = " ".join([str(x) for x in image_shape])

    res_complexity = os.path.join(work_dir, "complexity.json")
    update_config = ' '.join([f'{k}={v}' for k, v in update_config.items()])
    update_config = f' --update_config {update_config}' if update_config else ''
    subprocess.run(
        f'python {MMDETECTION_TOOLS}/get_flops.py'
        f' {config_path}'
        f' --shape {image_shape}'
        f' --out {res_complexity}'
        f'{update_config}'.split(' '), check=True)
    with open(res_complexity) as read_file:
        content = json.load(read_file)
    return content


def run_with_termination(cmd):
    process = subprocess.Popen(cmd, stderr=subprocess.PIPE)

    nbsr_err = NonBlockingStreamReader(process.stderr)

    failure_word = 'CUDA out of memory'
    while process.poll() is None:
        stderr = nbsr_err.readline(0.1)
        if stderr is None:
            time.sleep(1)
            continue
        stderr = stderr.decode('utf-8')
        print(stderr, end='')
        sys.stdout.flush()
        if failure_word in stderr:
            try:
                print('\nTerminated because of:', failure_word)
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            except ProcessLookupError as e:
                print(e)


def get_work_dir(cfg, update_config):
    overridden_work_dir = update_config.get('work_dir', None)
    return overridden_work_dir[0][1] if overridden_work_dir else cfg.work_dir
