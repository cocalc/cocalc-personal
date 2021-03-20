
set -v
sudo docker stop cocalc-personal
sudo docker rm cocalc-personal
sudo docker push  sagemathinc/cocalc-personal:latest
sudo docker push  sagemathinc/cocalc-personal:`cat current_commit`
