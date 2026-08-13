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
exports.activate = activate;
exports.deactivate = deactivate;
const vscode = __importStar(require("vscode"));
const backendClient_1 = require("./backendClient");
const treeProvider_1 = require("./treeProvider");
function activate(context) {
    const backend = new backendClient_1.BackendClient(context);
    const provider = new treeProvider_1.JavaRunProvider(backend);
    const output = vscode.window.createOutputChannel('Java Run');
    const log = (message) => {
        output.appendLine(message);
    };
    context.subscriptions.push(backend, output, vscode.window.registerTreeDataProvider('javaRunExplorer', provider), backend.onEvent(event => {
        if (event.type === 'log')
            log(event.message || '');
    }));
    const currentWorkspaceFile = () => {
        const file = vscode.workspace.workspaceFile;
        return file ? file.fsPath : undefined;
    };
    const syncWorkspace = async () => {
        const workspace = currentWorkspaceFile();
        if (workspace)
            await backend.request('switchWorkspace', { workspace });
    };
    const syncSettings = async () => {
        const timeout = vscode.workspace
            .getConfiguration('javaRun')
            .get('tomcatStartupTimeout', 450);
        await backend.request('setTomcatStartupTimeout', { seconds: timeout });
    };
    const refresh = async () => {
        try {
            await syncWorkspace();
            await syncSettings();
        }
        catch (error) {
            log(`[CONFIG] ${error instanceof Error ? error.message : String(error)}`);
        }
        await provider.refresh();
    };
    const register = (command, handler) => {
        context.subscriptions.push(vscode.commands.registerCommand(command, handler));
    };
    register('javaRun.refresh', refresh);
    register('javaRun.selectWorkspace', async () => {
        const result = await vscode.window.showOpenDialog({
            canSelectFiles: true,
            canSelectFolders: false,
            canSelectMany: false,
            filters: { 'VS Code Workspace': ['code-workspace'] }
        });
        if (!result?.[0])
            return;
        await backend.request('switchWorkspace', { workspace: result[0].fsPath });
        await syncSettings();
        await provider.refresh();
    });
    register('javaRun.buildInstall', async (node) => runBuild('install', node));
    register('javaRun.buildClean', async (node) => runBuild('clean', node));
    register('javaRun.buildCleanInstall', async (node) => runBuild('clean_install', node));
    register('javaRun.buildInstallAll', async () => runBuild('install_all'));
    register('javaRun.buildCleanAll', async () => runBuild('clean_all'));
    register('javaRun.buildCleanInstallAll', async () => runBuild('clean_install_all'));
    async function runBuild(action, node) {
        try {
            await syncWorkspace();
            const isAll = action.endsWith('_all');
            if (!isAll && !node?.data?.path) {
                throw new Error('Maven project harus dipilih.');
            }
            const projects = isAll ? undefined : [{ name: node.data.name, path: node.data.path }];
            const result = await backend.request('build', { action, ...(projects ? { projects } : {}) });
            vscode.window.showInformationMessage(`Maven ${action} selesai.`);
            log(`[BUILD] ${JSON.stringify(result)}`);
            await provider.refresh();
        }
        catch (error) {
            vscode.window.showErrorMessage(error instanceof Error ? error.message : String(error));
        }
    }
    register('javaRun.tomcatAdd', async () => {
        try {
            await syncWorkspace();
            const state = await backend.request('state');
            const suggested = `Tomcat-${(state.tomcats?.length || 0) + 1}`;
            const name = await vscode.window.showInputBox({
                prompt: 'Tomcat instance name',
                value: suggested,
                validateInput: value => value.trim() ? undefined : 'Nama instance wajib diisi.'
            });
            if (!name)
                return;
            await backend.request('tomcatAdd', { name });
            await provider.refresh();
        }
        catch (error) {
            vscode.window.showErrorMessage(error instanceof Error ? error.message : String(error));
        }
    });
    register('javaRun.tomcatRemove', async (node) => {
        if (!node?.data?.name)
            return;
        const confirm = await vscode.window.showWarningMessage(`Remove Tomcat instance "${node.data.name}"?`, { modal: true }, 'Remove');
        if (confirm !== 'Remove')
            return;
        try {
            await backend.request('tomcatRemove', { name: node.data.name });
            await provider.refresh();
        }
        catch (error) {
            vscode.window.showErrorMessage(error instanceof Error ? error.message : String(error));
        }
    });
    register('javaRun.tomcatStart', async (node) => runTomcat(node, false));
    register('javaRun.tomcatDebug', async (node) => runTomcat(node, true));
    async function runTomcat(node, debug) {
        if (!node?.data?.name)
            return;
        try {
            await syncWorkspace();
            await syncSettings();
            const workspaceFile = currentWorkspaceFile();
            if (debug && !workspaceFile) {
                throw new Error('File .code-workspace aktif tidak ditemukan. Buka workspace multi-root sebelum menjalankan Debug Tomcat.');
            }
            const result = await backend.request(debug ? 'tomcatDebug' : 'tomcatStart', {
                name: node.data.name,
                startupTimeout: node.data.startupTimeout,
                ...(debug && workspaceFile ? { workspaceFile } : {})
            });
            if (debug) {
                const debugConfiguration = result?.debugConfiguration;
                if (!debugConfiguration) {
                    throw new Error(`Konfigurasi Debug untuk ${node.data.name} tidak tersedia.`);
                }
                const started = await vscode.debug.startDebugging(undefined, debugConfiguration);
                if (!started) {
                    throw new Error(`Tomcat ${node.data.name} sudah berjalan dalam JPDA, ` +
                        `tetapi VS Code gagal melakukan Java Debug attach ` +
                        `ke localhost:${debugConfiguration.port}.`);
                }
                vscode.window.showInformationMessage(`Tomcat ${node.data.name} berjalan dalam debug mode. VS Code attach ke localhost:${debugConfiguration.port}.`);
            }
            else {
                vscode.window.showInformationMessage(`Tomcat ${node.data.name} startup completed.`);
            }
            await provider.refresh();
        }
        catch (error) {
            vscode.window.showErrorMessage(error instanceof Error ? error.message : String(error));
            await provider.refresh();
        }
    }
    register('javaRun.tomcatStop', async (node) => {
        if (!node?.data?.name)
            return;
        try {
            await backend.request('tomcatStop', { name: node.data.name });
            await provider.refresh();
        }
        catch (error) {
            vscode.window.showErrorMessage(error instanceof Error ? error.message : String(error));
        }
    });
    register('javaRun.deploy', async (node) => {
        if (!node?.data?.path)
            return;
        try {
            await syncWorkspace();
            const state = await backend.request('state');
            if (!state.tomcats?.length)
                throw new Error('Minimal satu Tomcat instance harus tersedia.');
            const selectedTomcat = await vscode.window.showQuickPick(state.tomcats.map((t) => ({
                label: String(t.name),
                description: t.running ? `running · HTTP ${t.ports?.http ?? '-'}` : 'stopped',
                value: String(t.name)
            })), { placeHolder: 'Pilih Tomcat instance' });
            if (!selectedTomcat)
                return;
            const artifacts = await backend.request('listArtifacts', { project: node.data.path });
            if (!artifacts.length) {
                throw new Error(`Tidak ada exploded web artifact di ${node.data.path}\target. Jalankan Maven Install terlebih dahulu.`);
            }
            const selectedArtifact = await vscode.window.showQuickPick(artifacts.map((a) => ({
                label: a.name,
                description: `${a.path}${a.wsProperties ? ' · WEB-INF/ws.properties ✓' : ' · WEB-INF/ws.properties not found'}`,
                value: a.name
            })), { placeHolder: 'Pilih exploded artifact', matchOnDescription: true });
            if (!selectedArtifact)
                return;
            const contextName = await vscode.window.showInputBox({
                prompt: 'Deployment context',
                value: selectedArtifact.value,
                validateInput: value => /^[A-Za-z0-9._-]+$/.test(value.trim()) ? undefined : 'Context hanya boleh berisi huruf, angka, ., _ atau -.'
            });
            if (!contextName)
                return;
            await backend.request('deploy', {
                instance: selectedTomcat.value,
                project: node.data.path,
                target: selectedArtifact.value,
                context: contextName
            });
            vscode.window.showInformationMessage(`Deployed ${selectedArtifact.value} -> /${contextName} on ${selectedTomcat.value}.`);
            await provider.refresh();
        }
        catch (error) {
            vscode.window.showErrorMessage(error instanceof Error ? error.message : String(error));
        }
    });
    register('javaRun.undeploy', async (node) => {
        if (!node?.data?.instance || !node?.data?.context)
            return;
        const confirm = await vscode.window.showWarningMessage(`Undeploy /${node.data.context} from ${node.data.instance}?`, { modal: true }, 'Undeploy');
        if (confirm !== 'Undeploy')
            return;
        try {
            await backend.request('undeploy', {
                instance: node.data.instance,
                context: node.data.context
            });
            await provider.refresh();
        }
        catch (error) {
            vscode.window.showErrorMessage(error instanceof Error ? error.message : String(error));
        }
    });
    register('javaRun.tomcatConfigurePorts', async (node) => {
        if (!node?.data?.name)
            return;
        try {
            const ports = node.data.ports || {};
            const values = {};
            for (const key of ['http', 'https', 'ajp', 'shutdown', 'debug']) {
                const value = await vscode.window.showInputBox({
                    prompt: `${key.toUpperCase()} port`,
                    value: String(ports[key] ?? ''),
                    validateInput: value => /^\d+$/.test(value.trim()) && Number(value) >= 1 && Number(value) <= 65535 ? undefined : 'Port harus berupa angka 1-65535.'
                });
                if (value === undefined)
                    return;
                values[key] = Number(value);
            }
            const timeout = await vscode.window.showInputBox({
                prompt: 'Tomcat startup / debug timeout (seconds)',
                value: String(node.data.startupTimeout ?? 450),
                validateInput: value => /^\d+$/.test(value.trim()) && Number(value) >= 1 ? undefined : 'Timeout harus berupa angka minimal 1 detik.'
            });
            if (timeout === undefined)
                return;
            values.startupTimeout = Number(timeout);
            await backend.request('tomcatConfigurePorts', { name: node.data.name, ports: values });
            await provider.refresh();
        }
        catch (error) {
            vscode.window.showErrorMessage(error instanceof Error ? error.message : String(error));
        }
    });
    register('javaRun.tomcatCleanupDescriptors', async (node) => {
        if (!node?.data?.name)
            return;
        try {
            await backend.request('cleanupDescriptors', { name: node.data.name });
            await provider.refresh();
        }
        catch (error) {
            vscode.window.showErrorMessage(error instanceof Error ? error.message : String(error));
        }
    });
    register('javaRun.configureJava', () => configurePath('java_home', 'Java Home'));
    register('javaRun.configureMaven', () => configurePath('maven_home', 'Maven Home'));
    register('javaRun.configureTomcat', () => configurePath('tomcat_home', 'Tomcat Home'));
    async function configurePath(key, label) {
        try {
            const result = await vscode.window.showOpenDialog({ canSelectFiles: false, canSelectFolders: true, canSelectMany: false, openLabel: `Select ${label}` });
            if (!result?.[0])
                return;
            await backend.request('setConfig', { key, value: result[0].fsPath });
            await provider.refresh();
        }
        catch (error) {
            vscode.window.showErrorMessage(error instanceof Error ? error.message : String(error));
        }
    }
    register('javaRun.configure', async () => {
        await vscode.commands.executeCommand('workbench.action.openSettings', '@ext:sm-devops.java-run');
    });
    register('javaRun.openLogs', () => output.show(true));
    context.subscriptions.push(vscode.workspace.onDidChangeConfiguration(async (event) => {
        if (event.affectsConfiguration('javaRun.tomcatStartupTimeout')) {
            try {
                await syncSettings();
                await provider.refresh();
            }
            catch (error) {
                log(`[CONFIG] ${error instanceof Error ? error.message : String(error)}`);
            }
        }
    }));
    void refresh();
}
function deactivate() { }
//# sourceMappingURL=extension.js.map