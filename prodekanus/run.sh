#!/bin/bash
cd /home/tkammer/mail
source prodekanus/venv/bin/activate
source prodekanus/mailhole_key.env
MAILHOLE_KEY="$MAILHOLE_KEY" python -m tkmail
