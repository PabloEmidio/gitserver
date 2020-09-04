import io
import os
import shlex
import tempfile
import subprocess
from enum import Enum
from subprocess import PIPE

from fastapi import FastAPI
from starlette.requests import Request
from starlette.responses import StreamingResponse

TEMPDIR = tempfile.TemporaryDirectory()

app = FastAPI()


class Service(str, Enum):
    receive = 'git-receive-pack'
    upload = 'git-upload-pack'


@app.get('/{path}/info/refs')
async def inforefs(path: str, service: Service):
    path = os.path.join(TEMPDIR.name, path)

    # Create repo if does not exists
    if not os.path.exists(path):
        cmd = shlex.quote(path)
        cmd = f'git init --bare {cmd}'
        cmd = shlex.split(cmd)
        subprocess.run(cmd, check=True)

    # Get info
    cmd = shlex.quote(path)
    cmd = f'{service} --stateless-rpc --advertise-refs {path}'
    cmd = shlex.split(cmd)
    result = subprocess.run(cmd, stdout=PIPE, check=True)

    # Adapted from:
    #   https://github.com/schacon/grack/blob/master/lib/grack.rb
    data = b'# service=' + service.encode()
    datalen = len(data) + 4
    datalen = b'%04x' % datalen
    data = datalen + data + b'0000' + result.stdout
    data = io.BytesIO(data)

    # Return to git
    media = f'application/x-{service}-advertisement'
    return StreamingResponse(data, media_type=media)



@app.post('/{path}/{service}')
async def service(path: str, service: Service, req: Request):
    path = os.path.join(TEMPDIR.name, path)

    # Start service
    cmd = shlex.quote(path)
    cmd = f'{service} --stateless-rpc {path}'
    cmd = shlex.split(cmd)
    proc = subprocess.Popen(cmd, stdin=PIPE, stdout=PIPE)

    # Send data to it
    async for data in req.stream():
        proc.stdin.write(data)
    proc.stdin.close()
    proc.wait()

    # Get output
    data = proc.stdout

    # Return to git
    media = f'application/x-{service}-result'
    return StreamingResponse(data, media_type=media)
