#!/bin/bash

nohup sh $(pwd)/sync-zuul-log-to-s3.sh > sync-log.log 2>&1 </dev/null &
