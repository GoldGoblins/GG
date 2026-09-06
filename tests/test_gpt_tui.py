import json,os,sys,time,tempfile
os.environ['QT_QPA_PLATFORM']='offscreen'
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[1]))
from pathlib import Path
from unittest.mock import patch
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlEngine,QQmlComponent
from PySide6.QtCore import QUrl,QObject
from backend.chat_surface_host import ChatSurfaceHost
from backend.desktop_settings import normalize_settings
assert normalize_settings({"engineTarget":"GPT_TUI"})["engineTarget"] == "GPT_TUI"
app=QGuiApplication([])
engine=QQmlEngine()
for name in ['Main.qml','components/ContextComposer.qml','components/SettingsChatModule.qml','components/TelemetryRail.qml']:
 c=QQmlComponent(engine,QUrl.fromLocalFile(str(Path(__file__).resolve().parents[1] / 'qml' / name)))
 assert not c.isError(), [e.toString() for e in c.errors()]
print('QML compilation PASS')
from backend.codex_wallet import snapshot as codex_wallet_snapshot
with tempfile.TemporaryDirectory() as d:
 wallet_session=Path(d)/'wallet.jsonl'
 wallet_session.write_text(json.dumps({'payload':{'type':'token_count','info':{'total_token_usage':{'total_tokens':10},'last_token_usage':{'input_tokens':8,'total_tokens':9},'model_context_window':100},'rate_limits':{'primary':{'used_percent':4.0,'resets_at':4102444800},'secondary':{'used_percent':0.0}}}})+'\n')
 wallet=codex_wallet_snapshot(wallet_session)
 assert wallet['live_tokens'] == 4
 assert wallet['live_reset_at'] == 4102444800
 assert wallet['live_reset_label'] != '—'
print('GPT wallet LIVE bar/reset data PASS')
class Grid:
 def __init__(self): self.output=b''
 def feed_bytes(self,b): self.output+=b
host=ChatSurfaceHost();host._gpt_grid=Grid();host._gpt_size=(80,24)
host._sessions['ws.tui.gpt']={'master':123}
with patch('backend.chat_surface_host.os.write') as write:
 for chunk in ['/', 'model', '\n', 'hej / världen', '\n']:
  assert host.writeChatTerminal('ws.tui.gpt',chunk)
 assert b''.join(call.args[1] for call in write.call_args_list) == b'/model\nhej / v\xc3\xa4rlden\n'
del host._sessions['ws.tui.gpt']
host._track_gpt_input('/flush\n')
assert host._commands_from_gpt_output("Unrecognized command '/flu") == []
assert host._commands_from_gpt_output("sh'. Type '/' for commands.") == ['/flush']
assert host._commands_from_gpt_output("nothing more") == []
host._track_gpt_input("/remember it's mine\n")
assert host._commands_from_gpt_output("Unrecognized command '/remember'.") == ["/remember it's mine"]
print('GPT slash input/native commands/split local command detection PASS')
from backend import gpt_memory_commands
with tempfile.TemporaryDirectory() as d:
 memory_root=Path(d)/'memory';session=Path(d)/'session.jsonl'
 rows=[
  {'type':'response_item','payload':{'type':'message','role':'developer','content':[{'type':'input_text','text':'hidden'}]}},
  {'type':'response_item','payload':{'type':'message','role':'user','content':[{'type':'input_text','text':'hello'}]}},
  {'type':'response_item','payload':{'type':'message','role':'assistant','content':[{'type':'output_text','text':'world'}]}},
 ]
 session.write_text('\n'.join(json.dumps(row) for row in rows)+'\n')
 with patch('backend.gpt_memory_commands._session_path',return_value=session), patch('backend.gpt_memory_commands._write_root',return_value=memory_root):
  result=gpt_memory_commands.run('/flush')
 assert '(1 prompts, 1 replies)' in result,result
 saved=list((memory_root/'sessions').glob('*.md'))
 assert len(saved)==1 and 'hello' in saved[0].read_text() and 'world' in saved[0].read_text()
print('GPT /flush transcript persistence PASS')
with tempfile.TemporaryDirectory() as d:
 exe=Path(d)/'codex';exe.write_text('#!/usr/bin/python3\nimport sys\nprint("GPT_TEST_READY",flush=True)\nfor line in sys.stdin:\n print("ECHO:"+line,flush=True)\n');exe.chmod(0o755)
 with patch('backend.chat_surface_host.shutil.which',return_value=str(exe)):
  host._start_gpt_tui();proc=host._sessions['ws.tui.gpt']['proc']
  host._start_gpt_tui();assert host._sessions['ws.tui.gpt']['proc'] is proc
  host._resize_gpt_tui(100,40)
  host.writeChatTerminal('ws.tui.gpt','hej\n')
  until=time.monotonic()+2
  while time.monotonic()<until and b'ECHO:hej' not in host._gpt_grid.output:
   app.processEvents();time.sleep(.01)
  assert b'ECHO:hej' in host._gpt_grid.output,host._gpt_grid.output
  host._close('ws.tui.gpt')
  proc.wait(timeout=3)
host._gpt_grid=None;host.shutdown()
host_src=Path(__import__('backend.chat_surface_host',fromlist=['__file__']).__file__).read_text()
assert '"--no-alt-screen"' in host_src
print('GPT PTY start, reuse, input/output, resize, cleanup PASS')
