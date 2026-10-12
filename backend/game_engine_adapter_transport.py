"""Bounded request transport shared by the native UI and format workers."""
from __future__ import annotations
import json,os,select,selectors,subprocess,threading,time,weakref
MAX_MESSAGE=16*1024*1024
def stop_worker(process):
    if process.poll() is None:
        process.terminate()
        try:process.wait(timeout=.3)
        except subprocess.TimeoutExpired:process.kill();process.wait(timeout=1)
    for pipe in (process.stdin,process.stdout,process.stderr):
        if pipe:pipe.close()
class BoundedWorker:
    def _start_worker(self,command,env):
        self.process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,env=env,bufsize=0)
        self._finalizer=weakref.finalize(self,stop_worker,self.process);self._lock=threading.Lock();self._pending=b'';self.closed=False
        self._selector=selectors.DefaultSelector();self._selector.register(self.process.stdout,selectors.EVENT_READ)
    def request(self,op,*,timeout=.3,**kwargs):
        with self._lock:
            if self.closed:raise RuntimeError('Native worker stopped')
            if self.process.poll() is not None:self.close();raise RuntimeError('Native worker stopped')
            packet=json.dumps({'op':op,**kwargs},ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()+b'\n'
            if len(packet)>MAX_MESSAGE:raise ValueError('Native message capacity exceeded')
            deadline=time.monotonic()+timeout;fd=self.process.stdin.fileno();os.set_blocking(fd,False);at=0
            while at<len(packet):
                remaining=deadline-time.monotonic()
                if remaining<=0 or not select.select([], [fd], [], max(0,remaining))[1]:return self._timeout('Native worker exceeded its time budget: '+op)
                try:at+=os.write(fd,packet[at:at+65536])
                except BlockingIOError:continue
                except BrokenPipeError:self.close();raise RuntimeError('Native worker stopped') from None
            while b'\n' not in self._pending:
                remaining=deadline-time.monotonic()
                if remaining<=0 or not self._selector.select(max(0,remaining)):return self._timeout('Native worker exceeded its time budget: '+op)
                chunk=os.read(self.process.stdout.fileno(),65536)
                if not chunk:self.close();raise RuntimeError('Native worker exited')
                self._pending+=chunk
                if len(self._pending)>MAX_MESSAGE:return self._timeout('Native response capacity exceeded')
            line,self._pending=self._pending.split(b'\n',1);answer=json.loads(line)
            if not answer['ok']:raise ValueError(answer.get('error','Native worker error'))
            return answer.get('result')
    def _timeout(self,message='Native worker exceeded its time budget'):
        self.close();raise TimeoutError(message)
    def close(self):
        if self.closed:return
        self.closed=True;self._selector.close();self._finalizer()
