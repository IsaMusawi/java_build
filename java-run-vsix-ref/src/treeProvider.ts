import * as vscode from 'vscode';
import { BackendClient } from './backendClient';

export type NodeKind = 'root' | 'configSection' | 'config' | 'projectSection' | 'project' | 'tomcatSection' | 'tomcat' | 'deployment';

export class JavaRunNode extends vscode.TreeItem {
  constructor(
    public readonly kind: NodeKind,
    public readonly data: any,
    label: string,
    collapsible: vscode.TreeItemCollapsibleState
  ) {
    super(label, collapsible);

    if (kind === 'root') {
      this.contextValue = 'root';
      this.iconPath = new vscode.ThemeIcon('tools');
    } else if (kind === 'configSection') {
      this.contextValue = 'configSection';
      this.iconPath = new vscode.ThemeIcon('settings-gear');
    } else if (kind === 'config') {
      this.contextValue = `config-${data.key}`;
      this.iconPath = new vscode.ThemeIcon(data.key === 'java_home' ? 'symbol-class' : data.key === 'maven_home' ? 'package' : 'server');
      this.description = data.value || 'Not configured';
      this.tooltip = data.value || 'Not configured';
    } else if (kind === 'projectSection') {
      this.contextValue = 'projectSection';
      this.iconPath = new vscode.ThemeIcon('project');
    } else if (kind === 'project') {
      this.contextValue = 'project';
      this.iconPath = new vscode.ThemeIcon('package');
      this.tooltip = data.path;
    } else if (kind === 'tomcatSection') {
      this.contextValue = 'tomcatSection';
      this.iconPath = new vscode.ThemeIcon('server-environment');
    } else if (kind === 'tomcat') {
      this.contextValue = 'tomcat';
      this.iconPath = new vscode.ThemeIcon(data.running ? 'debug-start' : 'server-environment');
      const http = data.ports?.http ?? '-';
      this.description = `${data.running ? 'running' : 'stopped'} · HTTP ${http}`;
      this.tooltip = `${data.name}\nCATALINA_HOME: ${data.home || 'not configured'}\nCATALINA_BASE: ${data.base || 'not configured'}\nHTTP: ${http}\nHTTPS: ${data.ports?.https ?? '-'}\nAJP: ${data.ports?.ajp ?? '-'}\nShutdown: ${data.ports?.shutdown ?? '-'}\nJPDA: ${data.ports?.debug ?? '-'}`;
    } else if (kind === 'deployment') {
      this.contextValue = 'deployment';
      this.iconPath = new vscode.ThemeIcon('globe');
      this.description = data.target || '';
    }
  }
}

export class JavaRunProvider implements vscode.TreeDataProvider<JavaRunNode> {
  private change = new vscode.EventEmitter<JavaRunNode | undefined | null | void>();
  readonly onDidChangeTreeData = this.change.event;
  private state: any = { config: {}, projects: [], tomcats: [] };

  constructor(private backend: BackendClient) {}

  async refresh() {
    try {
      this.state = await this.backend.request('state');
    } catch {
      this.state = { config: {}, projects: [], tomcats: [] };
    }
    this.change.fire();
  }

  getTreeItem(element: JavaRunNode): vscode.TreeItem { return element; }

  async getChildren(element?: JavaRunNode): Promise<JavaRunNode[]> {
    if (!element) {
      const workspace = this.state.config?.workspace;
      return [new JavaRunNode(
        'root',
        this.state.config,
        workspace ? workspace.split(/[\\/]/).pop() || 'Workspace' : 'Java Run',
        vscode.TreeItemCollapsibleState.Expanded
      )];
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
      return (this.state.projects || []).map((p: any) => new JavaRunNode('project', p, p.name, vscode.TreeItemCollapsibleState.None));
    }

    if (element.kind === 'tomcatSection') {
      return (this.state.tomcats || []).map((t: any) => new JavaRunNode('tomcat', t, t.name, vscode.TreeItemCollapsibleState.Collapsed));
    }

    if (element.kind === 'tomcat') {
      return Object.entries(element.data.deployments || {}).map(([context, d]) =>
        new JavaRunNode('deployment', { context, ...(d as any), instance: element.data.name }, `/${context}`, vscode.TreeItemCollapsibleState.None)
      );
    }

    return [];
  }
}
