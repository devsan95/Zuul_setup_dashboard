#!/usr/bin/env bash
kill -SIGHUP `supervisorctl pid zuul-server`