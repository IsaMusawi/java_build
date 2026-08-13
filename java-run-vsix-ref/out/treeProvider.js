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
exports.JavaRunProvider = exports.JavaRunNode = void 0;
const vscode = __importStar(require("vscode"));
class JavaRunNode extends vscode.TreeItem {
    constructor(kind, data, label, collapsible) {
        super(label, collapsible);
        this.kind = kind;
        this.data = data;
        if (kind === 'root') {
            this.contextValue = 'root';
            this.iconPath = new vscode.ThemeIcon('tools');
        }
        else if (kind === 'configSection') {
            this.contextValue = 'configSection';
            this.iconPath = new vscode.ThemeIcon('settings-gear');
        }
        else if (kind === 'config') {
            this.contextValue = `config-${data.key}`;
            this.iconPath = new vscode.ThemeIcon(data.key === 'java_home' ? 'symbol-class' : data.key === 'maven_home' ? 'package' : 'server');
            this.description = data.value || 'Not configured';
            this.tooltip = data.value || 'Not configured';
        }
        else if (kind === 'projectSection') {
            this.contextValue = 'projectSection';
            this.iconPath = new vscode.ThemeIcon('project');
        }
        else if (kind === 'project') {
            this.contextValue = 'project';
            this.iconPath = new vscode.ThemeIcon('package');
            this.tooltip = data.path;
        }
        else if (kind === 'tomcatSection') {
            this.contextValue = 'tomcatSection';
            this.iconPath = new vscode.ThemeIcon('server-environment');
        }
        else if (kind === 'tomcat') {
            this.contextValue = 'tomcat';
            this.iconPath = new vscode.ThemeIcon(data.running ? 'debug-start' : 'server-environment');
            const http = data.ports?.http ?? '-';
            this.description = `${data.running ? 'running' : 'stopped'} · HTTP ${http}`;
            this.tooltip = `${data.name}\nCATALINA_HOME: ${data.home || 'not configured'}\nCATALINA_BASE: ${data.base || 'not configured'}\nHTTP: ${http}\nHTTPS: ${data.ports?.https ?? '-'}\nAJP: ${data.ports?.ajp ?? '-'}\nShutdown: ${data.ports?.shutdown ?? '-'}\nJPDA: ${data.ports?.debug ?? '-'}`;
        }
        else if (kind === 'deployment') {
            this.contextValue = 'deployment';
            this.iconPath = new vscode.ThemeIcon('globe');
            this.description = data.target || '';
        }
    }
}
exports.JavaRunNode = JavaRunNode;
class JavaRunProvider {
    constructor(backend) {
        this.backend = backend;
        this.change = new vscode.EventEmitter();
        this.onDidChangeTreeData = this.change.event;
        this.state = { config: {}, projects: [], tomcats: [] };
    }
    async refresh() {
        try {
            this.state = await this.backend.request('state');
        }
        catch {
            this.state = { config: {}, projects: [], tomcats: [] };
        }
        this.change.fire();
    }
    getTreeItem(element) { return element; }
    async getChildren(element) {
        if (!element) {
            const workspace = this.state.config?.workspace;
            return [new JavaRunNode('root', this.state.config, workspace ? workspace.split(/[\\/]/).pop() || 'Workspace' : 'Java Run', vscode.TreeItemCollapsibleState.Expanded)];
        }
        if (element.kind === 'root') {
            return [
                new JavaRunNode('configSection', this.state.config, 'Configuration', vscode.TreeItemCollapsibleState.Expanded),
                new JavaRunNode('projectSection', { section: 'projects' }, `Maven Projects (${(this.state.projects || []).length})`, vscode.TreeItemCollapsibleState.Expanded),
                new JavaRunNode('tomcatSection', { section: 'instances' }, `Tomcat Instances (${(this.state.tomcats || []).length})`, vscode.TreeItemCollapsibleState.Expanded),
            ];
        }
        if (element.kind === 'configSection') {
            const c = this.state.config || {};
            return [
                new JavaRunNode('config', { key: 'workspace_path', value: c.workspace || '' }, 'Workspace', vscode.TreeItemCollapsibleState.None),
                new JavaRunNode('config', { key: 'java_home', value: c.javaHome || '' }, 'Java Home', vscode.TreeItemCollapsibleState.None),
                new JavaRunNode('config', { key: 'maven_home', value: c.mavenHome || '' }, 'Maven Home', vscode.TreeItemCollapsibleState.None),
                new JavaRunNode('config', { key: 'tomcat_home', value: c.tomcatHome || '' }, 'Tomcat Home', vscode.TreeItemCollapsibleState.None),
            ];
        }
        if (element.kind === 'projectSection') {
            return (this.state.projects || []).map((p) => new JavaRunNode('project', p, p.name, vscode.TreeItemCollapsibleState.None));
        }
        if (element.kind === 'tomcatSection') {
            return (this.state.tomcats || []).map((t) => new JavaRunNode('tomcat', t, t.name, vscode.TreeItemCollapsibleState.Collapsed));
        }
        if (element.kind === 'tomcat') {
            return Object.entries(element.data.deployments || {}).map(([context, d]) => new JavaRunNode('deployment', { context, ...d, instance: element.data.name }, `/${context}`, vscode.TreeItemCollapsibleState.None));
        }
        return [];
    }
}
exports.JavaRunProvider = JavaRunProvider;
//# sourceMappingURL=treeProvider.js.map