import * as cp from 'child_process';
import * as path from 'path';
import * as vscode from 'vscode';
import * as readline from 'readline';

export type BackendEvent = { type: string; [key: string]: any };

export class BackendClient implements vscode.Disposable {
  private proc?: cp.ChildProcessWithoutNullStreams;
  private seq = 0;
  private pending = new Map<number, { resolve: (v: any) => void; reject: (e: any) => void }>();
  private emitter = new vscode.EventEmitter<BackendEvent>();
  readonly onEvent = this.emitter.event;

  constructor(private context: vscode.ExtensionContext) {}

  async start(): Promise<void> {
    if (this.proc) return;
    const configured = vscode.workspace.getConfiguration('javaRun').get<string>('pythonExecutable', '');
    const python = configured || (process.platform === 'win32' ? 'python' : 'python3');
    const script = path.join(this.context.extensionPath, 'backend', 'server.py');
    this.proc = cp.spawn(python, [script], { cwd: path.dirname(script), windowsHide: true });
    const rl = readline.createInterface({ input: this.proc.stdout });
    rl.on('line', line => {
      try {
        const message = JSON.parse(line) as BackendEvent;
        if (message.type === 'response') {
          const p = this.pending.get(message.id);
          if (!p) return;
          this.pending.delete(message.id);
          message.ok ? p.resolve(message.result) : p.reject(new Error(message.error || 'Backend error'));
        } else {
          this.emitter.fire(message);
        }
      } catch (e) {
        this.emitter.fire({ type: 'log', message: `[BACKEND] Invalid message: ${line}` });
      }
    });
    this.proc.stderr.on('data', data => this.emitter.fire({ type: 'log', message: `[BACKEND] ${String(data).trimEnd()}` }));
    this.proc.on('exit', code => {
      this.proc = undefined;
      for (const p of this.pending.values()) p.reject(new Error(`Backend exited: ${code}`));
      this.pending.clear();
    });
  }

  async request<T = any>(action: string, params: any = {}): Promise<T> {
    await this.start();
    if (!this.proc) throw new Error('Backend process is not running.');
    const id = ++this.seq;
    const payload = JSON.stringify({ id, action, params }) + '\n';
    return new Promise<T>((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.proc!.stdin.write(payload, err => {
        if (err) {
          this.pending.delete(id);
          reject(err);
        }
      });
    });
  }

  dispose(): void {
    this.proc?.kill();
    this.proc = undefined;
    this.emitter.dispose();
  }
}
