#!/usr/bin/env bash
set -ex

sudo docker stop cocalc-personal && sudo docker rm cocalc-personal
git pull
commit=`git ls-remote -h https://github.com/sagemathinc/cocalc master | awk '{print $1}'`
echo $commit | cut -c-12 > current_commit
time sudo docker build --no-cache  --build-arg commit=$commit -t cocalc $@ .
sudo docker tag cocalc-personal:latest sagemathinc/cocalc-personal:latest
sudo docker tag cocalc-personal:latest sagemathinc/cocalc-personal:`cat current_commit`
sudo docker run --name=cocalc-personal -d -p 8000:80 sagemathinc/cocalc-personal
