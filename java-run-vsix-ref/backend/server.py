import os

from build_manager import BuildManager
from config_manager import ConfigManager
from protocol import run_loop
from tomcat_manager import TomcatManager


config = ConfigManager()


def emit(message):
    import json
    import sys
    sys.stdout.write(json.dumps(message, ensure_ascii=True) + "\n")
    sys.stdout.flush()


tomcat = TomcatManager(config, emit)
builder = BuildManager(config, emit)


def state():
    projects = config.get_projects_from_workspace()
    tomcats = []
    for name in config.get_active_tabs():
        try:
            tomcats.append(tomcat.instance(name))
        except Exception:
            continue

    summary = config.summary()
    return {
        "config": {
            **summary,
            "tomcatStartupTimeout": config.get_tomcat_startup_timeout(),
        },
        "projects": projects,
        "tomcats": tomcats,
    }


def require_instance(name):
    if not name:
        raise ValueError("Tomcat instance harus dipilih.")
    if name not in config.get_active_tabs():
        raise ValueError(f"Tomcat instance tidak ditemukan: {name}")
    return name


def dispatch(action, params):
    if action == "state":
        return state()

    if action == "switchWorkspace":
        config.switch_workspace(params.get("workspace", ""))
        return state()

    # Backward-compatible global/default timeout setting.
    if action == "setTomcatStartupTimeout":
        value = config.set_tomcat_startup_timeout(params.get("seconds"))
        return {"seconds": value}

    if action == "setConfig":
        key = str(params.get("key", "")).strip()
        value = params.get("value", "")
        if key not in {"java_home", "maven_home", "tomcat_home"}:
            raise ValueError(f"Unsupported configuration key: {key}")
        config.set(key, value)
        return state()

    if action == "build":
        requested_projects = params.get("projects")
        projects = requested_projects if requested_projects is not None else None
        return builder.build(params.get("action", "install"), projects)

    if action == "listArtifacts":
        project = params.get("project", "")
        if not project:
            raise ValueError("Project harus dipilih.")
        return tomcat.list_exploded_artifacts(project)

    if action == "tomcatAdd":
        name = config.add_instance(params.get("name", ""))
        return {
            "name": name,
            "base": config.get_instance_base(name),
            "ports": config.get_instance_ports(name),
            "startupTimeout": config.get_instance_startup_timeout(name),
        }

    if action == "tomcatRemove":
        name = require_instance(params.get("name", ""))
        if tomcat.is_running(name):
            raise RuntimeError(f"Tomcat {name} sedang berjalan. Stop Tomcat terlebih dahulu.")
        result = config.remove_instance(name)
        return {"removed": name, "result": result}

    if action in {"tomcatStart", "tomcatDebug"}:
        name = require_instance(params.get("name", ""))
        timeout = params.get("startupTimeout")
        return tomcat.start(
            name,
            debug=action == "tomcatDebug",
            startup_timeout=timeout,
            workspace_file=params.get(
                'workspaceFile',
                params.get('workspaceFolder', ''),
            ),
        )

    if action == "tomcatStop":
        return tomcat.stop(require_instance(params.get("name", "")))

    if action == "tomcatConfigurePorts":
        name = require_instance(params.get("name", ""))
        return {
            "name": name,
            **tomcat.save_ports(name, params.get("ports") or {}),
        }

    if action == "deploy":
        name = require_instance(params.get("instance", ""))
        project = params.get("project", "")
        context = params.get("context", "")
        target = params.get("target", "")
        if not project:
            raise ValueError("Project harus dipilih.")
        return tomcat.deploy(name, project, target, context)

    if action == "undeploy":
        name = require_instance(params.get("instance", ""))
        return tomcat.undeploy(name, params.get("context", ""))

    if action == "cleanupDescriptors":
        name = require_instance(params.get("name", ""))
        return tomcat.cleanup_untracked_descriptors(name)

    raise ValueError(f"Unknown backend action: {action}")


if __name__ == "__main__":
    run_loop(dispatch)
