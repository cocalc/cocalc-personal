#!/usr/bin/env python3

import os, tempfile, time, shutil, subprocess, sys

# Where the PostgreSQL data is stored
PGDATA = '/projects/postgres/data'
PGHOST  = os.path.join(PGDATA, 'socket')
os.environ['PGHOST'] = PGHOST
os.environ['PGUSER'] = 'smc'

# ensure that everything we spawn has this umask, which is more secure.
os.umask(0o077)

join = os.path.join

def log(*args):
    print(*args)
    sys.stdout.flush()

def run(v, shell=False, path='.', get_output=False, env=None, verbose=1):
    t = time.time()
    if isinstance(v, str):
        cmd = v
        shell = True
    else:
        cmd = ' '.join([(x if len(x.split())<=1 else '"%s"'%x) for x in v])
    if path != '.':
        cur = os.path.abspath(os.curdir)
        if verbose:
            print('chdir %s'%path)
        os.chdir(path)
    try:
        if verbose:
            print(cmd)
        if shell:
            kwds = {'shell':True, 'executable':'/bin/bash', 'env':env}
        else:
            kwds = {'env':env}
        if get_output:
            output = subprocess.Popen(v, stdout=subprocess.PIPE, **kwds).stdout.read().decode()
        else:
            if subprocess.call(v, **kwds):
                raise RuntimeError("error running '{cmd}'".format(cmd=cmd))
            output = None
        seconds = time.time() - t
        if verbose > 1:
            print("TOTAL TIME: {seconds} seconds -- to run '{cmd}'".format(seconds=seconds, cmd=cmd))
        return output
    finally:
        if path != '.':
            os.chdir(cur)

def self_signed_cert(target= 'nopassphrase.pem'):
    if os.path.exists('/projects/conf/nopassphrase.pem'):
        log("installing cert at '/projects/conf/nopassphrase.pem'")
        run("cp /projects/conf/nopassphrase.pem {target} && chmod og-rwx {target}".format(target=target))
        return
    log("create self_signed_cert")
    with tempfile.TemporaryDirectory() as tmp:
        run(['openssl', 'req', '-new', '-x509', '-nodes', '-out', 'server.crt',
                  '-keyout', 'server.key',
                  '-subj', '/C=US/ST=WA/L=WA/O=Network/OU=IT Department/CN=sagemath'], path=tmp)
        s  = open(join(tmp, 'server.crt')).read() + open(join(tmp, 'server.key')).read()
        open(target,'w').write(s)
        run("chmod og-rwx {target} && mkdir -p /projects/conf && cp {target} /projects/conf/nopassphrase.pem".format(target=target))

def init_projects_path():
    log("initialize /projects path")
    if not os.path.exists('/projects'):
        log("WARNING: container data will be EPHEMERAL -- in /projects")
        os.makedirs('/projects')
    # Ensure that users can see their own home directories:
    os.system("chmod a+rx /projects")
    for path in ['conf']:
        full_path = join('/projects', path)
        if not os.path.exists(full_path):
            log("creating ", full_path)
            os.makedirs(full_path)
            run("chmod og-rwx '%s'"%full_path)

def start_services():
    for name in ['haproxy', 'nginx', 'ssh']:
        run(['service', name, 'start'])


def root_ssh_keys():
    run("rm -rf /root/.ssh/")
    run("ssh-keygen -t ecdsa -N '' -f /root/.ssh/id_ecdsa")
    run("cp -v /root/.ssh/id_ecdsa.pub /root/.ssh/authorized_keys")

def start_hub():
    c = ". smc-env && hub start \
            --host=localhost \
            --port 5000 \
            --proxy_port 5001 \
            --share_port 5002 \
            --share_path='/projects/[project_id]' \
            --update \
            --single \
            --logfile /var/log/hub.log \
            --pidfile /run/hub.pid"
    if os.environ.get("COCALC_PERSONAL", False) == 'yes':
        print("COCALC_PERSONAL: setting hub to authenticate all connections as first user")
        c += '\\\n     --personal'
    run(c, path='/cocalc/src')

def personal_sudo():
    # When running in personal mode, make it so ALL users
    # can use sudo with no password.   We are assuming that
    # all projects have full access to the system and there
    # is only one user!
    if not os.environ.get("COCALC_PERSONAL", False) == "yes":
        print("COCALC_PERSONAL NOT set")
        run("rm -f /etc/sudoers.d/cocalc-personal")
        return
    print("COCALC_PERSONAL: giving ALL Linux users (i.e., projects) full sudo")
    run('echo "ALL ALL=NOPASSWD: ALL" > /etc/sudoers.d/cocalc-personal && chmod 0440 /etc/sudoers.d/cocalc-personal')

def postgres_perms():
    run("mkdir -p /projects/postgres && chown -R postgres. /projects/postgres && chmod og-rwx -R /projects/postgres")

def start_postgres():
    postgres_perms()
    if not os.path.exists(PGDATA):  # see comments in smc/src/dev/project/start_postgres.py
        run("sudo -u postgres /usr/lib/postgresql/13/bin/pg_ctl init -D '%s'"%PGDATA)
        open(os.path.join(PGDATA,'pg_hba.conf'), 'w').write("local all all trust")
        conf = os.path.join(PGDATA, 'postgresql.conf')
        s = open(conf).read() + "\nunix_socket_directories = '%s'\nlisten_addresses=''\n"%PGHOST
        open(conf,'w').write(s)
        os.makedirs(PGHOST)
        postgres_perms()
        run("sudo -u postgres /usr/lib/postgresql/13/bin/postgres -D '%s' >%s/postgres.log 2>&1 &"%(PGDATA, PGDATA))
        time.sleep(5)
        run("sudo -u postgres /usr/lib/postgresql/13/bin/createuser -h '%s' -sE smc"%PGHOST)
        run("sudo -u postgres kill %s"%(open(os.path.join(PGDATA, 'postmaster.pid')).read().split()[0]))
        time.sleep(3)
    os.system("sudo -u postgres /usr/lib/postgresql/13/bin/postgres -D '%s' > /var/log/postgres.log 2>&1 &"%PGDATA)

def reset_project_state():
    while True:
        try:
            run("""echo "update projects set state='{\\"state\\":\\"opened\\"}';" | psql -t""")
            return
        except:
            time.sleep(1)

def start_compute():
    # We always delete compute.sqlite3 (resetting it) since obviously all projects are stopped on container startup.
    run("mkdir -p /projects/conf && chmod og-rwx -R /projects/conf && rm -f /projects/conf/compute.sqlite3")
    run(". smc-env; compute --host=localhost --single start 1>/var/log/compute.log 2>/var/log/compute.err &", path='/cocalc/src')
    # Sleep to wait for compute server to start and write port/secret *AND* initialize the schema.
    # TODO: should really do this right -- since if the compute-client tries to initialize schema at same, time things get hosed.
    run("""sleep 15; . smc-env; echo "require('ts-node').register(); require('smc-hub/compute-client').compute_server(cb:(e,s)-> s._add_server_single(cb:->process.exit(0)))" | coffee & """, path='/cocalc/src')

def tail_logs():
    run("tail -f /var/log/compute.log /var/log/compute.err /cocalc/logs/*")

def main():
    personal_sudo()
    self_signed_cert('/run/haproxy.pem')
    init_projects_path()
    start_services()
    root_ssh_keys()
    start_postgres()
    start_hub()
    start_compute()
    reset_project_state()
    while True:
        os.wait()

if __name__ == "__main__":
    main()

