"""Reproducible source inventory for FileDialog entry points and UI action declarations."""
import ast,json
from pathlib import Path


def inventory(root):
    dialogs=[];controls=[];bindings=[]
    for path in sorted((Path(root)/'app/ui').glob('*.py')):
        source=path.read_text(encoding='utf-8-sig');tree=ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node,ast.Call):continue
            call=ast.unparse(node.func);name=call.rsplit('.',1)[-1]
            item=dict(file=path.relative_to(root).as_posix(),line=node.lineno,call=ast.get_source_segment(source,node))
            if name in ('getOpenFileName','getOpenFileNames','getExistingDirectory','getSaveFileName') and path.name!='dialogs.py':dialogs.append(item)
            if name in ('QPushButton','QToolButton','QAction','QShortcut','QDialogButtonBox','_button') or name=='button' and call.startswith(('self.button','p.button')) or name=='addAction' and call.startswith('menu.'):
                controls.append(item)
            if name=='connect':bindings.append(item)
    return dict(file_dialog_calls=dialogs,control_declarations=controls,signal_connections=bindings)


if __name__=='__main__':
    root=Path(__file__).resolve().parents[1];data=inventory(root)
    out=root/'build/ui-source-inventory.json';out.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    print({key:len(value) for key,value in data.items()})
