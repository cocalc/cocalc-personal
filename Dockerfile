FROM ubuntu:20.04

LABEL William Stein <wstein@sagemath.com>

USER root

# See https://github.com/sagemathinc/cocalc/issues/921
ENV LC_ALL=C.UTF-8 LANG=en_US.UTF-8 LANGUAGE=en_US:en TERM=screen

# This sets things so that hub runs in a mode with only one account
# and no sign in.  This is meant for personal use on a personal compute.
ENV COCALC_PERSONAL=yes

# So we can source (see http://goo.gl/oBPi5G)
RUN rm /bin/sh && ln -s /bin/bash /bin/sh

# Minimal ubuntu software that are needed to get CoCalc to build and run, and
# note much more.
RUN \
     apt-get update \
  && DEBIAN_FRONTEND=noninteractive apt-get upgrade -y \
  && DEBIAN_FRONTEND=noninteractive apt-get install -y \
       software-properties-common \
       liblog-log4perl-perl \
       flex \
       bison \
       libreadline-dev \
       net-tools \
       wget \
       git \
       python3 \
       python3-pip \
       make \
       g++ \
       sudo \
       psmisc \
       haproxy \
       nginx \
       rsync \
       vim \
       inetutils-ping \
       ssh \
       m4 \
       libpq5 \
       libpq-dev \
       build-essential \
       automake \
       dpkg-dev \
       libssl-dev \
       libcurl4-openssl-dev \
       smem \
       python3-yaml \
       python3-matplotlib \
       python3-jupyter* \
       python3-ipywidgets \
       python \
       jupyter \
       locales \
       locales-all \
       clang-format \
       yapf3 \
       nodejs \
       npm \
       libxml2-dev \
       libxslt-dev \
       libsqlite3-dev

# Install npm 7.x over /usr/bin/npm, which cocalc requires. (This is ugly!)
RUN npm install -g --prefix=/usr -f npm@7.3.0

# Commit to checkout and build.
ARG commit=HEAD

# Pull latest source code for CoCalc and checkout requested commit (or HEAD)
RUN \
     git clone https://github.com/sagemathinc/cocalc.git \
  && cd /cocalc && git pull && git fetch origin && git checkout ${commit:-HEAD}

# Build and install cocalc itself.
RUN \
     cd /cocalc/src \
  && . ./smc-env \
  && npm run make

# CRITICAL to install first web, then compute, since compute precompiles all the .js
# for fast startup, but unfortunately doing so breaks ./install.py all --web, since
# the .js files laying around somehow mess up cjsx loading.
# Generates the static web application:
RUN \
     cd /cocalc/src \
  && . ./smc-env \
  && ./install.py all --web

# Install specific to compute:
RUN \
     cd /cocalc/src && . ./smc-env \
  && ./install.py all --compute

# Clean up
RUN rm -rf /root/.npm /root/.node-gyp/

# Lock down generic systemwide default permission here, so that one project doesn't
# have read access to another by default.  We still want good separation between
# projects even for personal mode.
RUN echo "umask 077" >> /etc/bash.bashrc

# Build a UTF-8 locale, so that tmux works -- see https://unix.stackexchange.com/questions/277909/updated-my-arch-linux-server-and-now-i-get-tmux-need-utf-8-locale-lc-ctype-bu
RUN echo "en_US.UTF-8 UTF-8" > /etc/locale.gen && locale-gen

### Configuration
COPY login.defs /etc/login.defs
COPY login /etc/defaults/login
COPY nginx.conf /etc/nginx/sites-available/default
COPY haproxy.conf-personal /etc/haproxy/haproxy.cfg
COPY run.py /root/run.py
COPY bashrc /root/.bashrc

# CoCalc Jupyter widgets needs this
RUN \
  pip3 install --no-cache-dir ipyleaflet

# The Jupyter kernel that gets auto-installed with some other jupyter Ubuntu packages
# doesn't have some nice options regarding inline matplotlib (and possibly others), so
# we delete it and replace it with our own.
RUN rm -rf /usr/share/jupyter/kernels/python3
COPY kernels/python3-ubuntu /usr/local/share/jupyter/kernels/python3-ubuntu

RUN \
     sh -c 'echo "deb http://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" > /etc/apt/sources.list.d/pgdg.list' \
  && wget --quiet -O - https://www.postgresql.org/media/keys/ACCC4CF8.asc | apt-key add - \
  && apt-get update \
  && apt-get install -y  postgresql-13

CMD /root/run.py

ARG BUILD_DATE
LABEL org.label-schema.build-date=$BUILD_DATE

EXPOSE 22 80
