"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.BackendClient = void 0;
const cp = __importStar(require("child_process"));
const path = __importStar(require("path"));
const vscode = __importStar(require("vscode"));
const readline = __importStar(require("readline"));
class BackendClient {
    constructor(context) {
        this.context = context;
        this.seq = 0;
        this.pending = new Map();
        this.emitter = new vscode.EventEmitter();
        this.onEvent = this.emitter.event;
    }
    async start() {
        if (this.proc)
            return;
        const configured = vscode.workspace.getConfiguration('javaRun').get('pythonExecutable', '');
        const python = configured || (process.platform === 'win32' ? 'python' : 'python3');
        const script = path.join(this.context.extensionPath, 'backend', 'server.py');
        this.proc = cp.spawn(python, [script], { cwd: path.dirname(script), windowsHide: true });
        const rl = readline.createInterface({ input: this.proc.stdout });
        rl.on('line', line => {
            try {
                const message = JSON.parse(line);
                if (message.type === 'response') {
                    const p = this.pending.get(message.id);
                    if (!p)
                        return;
                    this.pending.delete(message.id);
                    message.ok ? p.resolve(message.result) : p.reject(new Error(message.error || 'Backend error'));
                }
                else {
                    this.emitter.fire(message);
                }
            }
            catch (e) {
                this.emitter.fire({ type: 'log', message: `[BACKEND] Invalid message: ${line}` });
            }
        });
        this.proc.stderr.on('data', data => this.emitter.fire({ type: 'log', message: `[BACKEND] ${String(data).trimEnd()}` }));
        this.proc.on('exit', code => {
            this.proc = undefined;
            for (const p of this.pending.values())
                p.reject(new Error(`Backend exited: ${code}`));
            this.pending.clear();
        });
    }
    async request(action, params = {}) {
        await this.start();
        if (!this.proc)
            throw new Error('Backend process is not running.');
        const id = ++this.seq;
        const payload = JSON.stringify({ id, action, params }) + '\n';
        return new Promise((resolve, reject) => {
            this.pending.set(id, { resolve, reject });
            this.proc.stdin.write(payload, err => {
                if (err) {
                    this.pending.delete(id);
                    reject(err);
                }
            });
        });
    }
    dispose() {
        this.proc?.kill();
        this.proc = undefined;
        this.emitter.dispose();
    }
}
exports.BackendClient = BackendClient;
//# sourceMappingURL=backendClient.js.map