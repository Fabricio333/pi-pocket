"""A bundled catalog with persistent installation state and lazy imports."""
import gc, importlib, json, sys
from pathlib import Path
from .ui import ROOT

class Registry:
    def __init__(self,state_dir):
        self.catalog=json.loads((ROOT/'catalog.json').read_text())
        self.by_id={a['id']:a for a in self.catalog}
        self.state=Path(state_dir)/'installed.json'
        self.state.parent.mkdir(parents=True,exist_ok=True)
        try:self.installed=set(json.loads(self.state.read_text())) & self.by_id.keys()
        except (OSError,ValueError):self.installed={'pay21'}
    def install(self,app_id):
        if app_id not in self.by_id:raise ValueError('Unknown app')
        self.installed.add(app_id);self.save()
    def uninstall(self,app_id):self.installed.discard(app_id);self.save()
    def save(self):
        temp=self.state.with_suffix('.tmp');temp.write_text(json.dumps(sorted(self.installed)));temp.replace(self.state)
    def open(self,app_id,context):
        if app_id not in self.installed:raise ValueError('App is not installed')
        module=importlib.import_module(self.by_id[app_id]['module'])
        return module.App(context)
    def unload(self,app_id):
        module=self.by_id[app_id]['module']
        loaded=sys.modules.pop(module,None)
        parent_name,attribute=module.rsplit('.',1)
        parent=sys.modules.get(parent_name)
        if loaded is not None and getattr(parent,attribute,None) is loaded:delattr(parent,attribute)
        gc.collect()
