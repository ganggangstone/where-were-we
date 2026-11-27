import support  # blocks real AI CLIs; drops an inherited WHERE_WERE_WE_SETTINGS
import unittest

import react_actions
import service_flow
import structure_index


class ReactActions(unittest.TestCase):
    def resolve(self, jsx, wrapper="export const api={save:()=>fetch('/save')};", edges=True):
        parse=structure_index._parser('javascript').parse
        api=parse(wrapper.encode()).root_node
        src=parse(jsx.encode()).root_node
        requests=service_flow.javascript_requests(api,'api.js')
        modules={'api.js':react_actions.facts(api,requests),'App.jsx':react_actions.facts(src,[])}
        links=[{'file':'App.jsx','line':1,'target':'api.js'}] if edges else []
        react_actions.attach(modules,links,requests)
        return [action for request in requests for action in request.get('actions',[])]

    def test_ui_handler_import_call_and_wrapper_are_all_required(self):
        code="""import {api} from './api.js';
function App() {
 function submit() { api.save() }
 return <form onSubmit={submit}/>;
}"""
        action,=self.resolve(code)
        self.assertEqual((action['event'],action['handler'],action['line'],action['call_line']),('onSubmit','submit',4,3))
        self.assertEqual(action['client_definition'],{'file':'api.js','line':1})
        self.assertEqual(self.resolve(code,edges=False),[])
        for changed in (code.replace('submit()','submit(api)'),
                        code.replace('api.save()','function never(){api.save()}'),
                        code.replace('onSubmit={submit}','onSubmit={submit} {...props}'),
                        code.replace('<form','<CustomForm')):
            self.assertEqual(self.resolve(changed),[])
        self.assertEqual(self.resolve(code,wrapper="export const api={save:()=>fetch('/save')};api.save=other;"),[])

    def test_local_import_of_an_exported_request_function(self):
        code="""import {save as send} from './api.js';
function Editor() {
 function submit() { send() }
 return <button onClick={()=>submit()}/>;
}"""
        action,=self.resolve(code,wrapper="export function save(){return fetch('/save')}")
        self.assertEqual(action['event'],'onClick')

    def test_literal_label_and_form_submitter_preserve_source_line(self):
        def event(markup):
            code="import {api} from './api.js';\nfunction App(){\nfunction go(){api.save()}\nreturn "+markup+";\n}"
            return self.resolve(code)[0]
        button=event('<button onClick={go}>Save</button>')
        self.assertEqual((button['label'],button['label_source']),('Save',{'file':'App.jsx','line':4}))
        self.assertEqual(event('<button onClick={go} aria-label="Delete">×</button>')['label'],'Delete')
        form=event('<form onSubmit={go}>\n<button type="submit">Add</button></form>')
        self.assertEqual((form['label'],form['label_source']['line']),('Add',5))
        for markup in ('<button onClick={go} aria-label={name}>×</button>',
                       '<button onClick={go}>{computed}</button>',
                       '<form onSubmit={go}><button type="submit">A</button><button type="submit">B</button></form>',
                       '<form onSubmit={go}><button type="submit" form="other">Elsewhere</button></form>',
                       '<form onSubmit={go}><button type="submit">A</button><div><button>B</button></div></form>',
                       '<input aria-labelledby="other" onChange={go}/>'):
            self.assertNotIn('label',event(markup))
