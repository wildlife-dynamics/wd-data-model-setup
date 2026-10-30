# ecoscope-workflows-ext-wdmodel

Tasks for provisioning the Wildlife Dynamics standard conservancy data model
onto an EarthRanger instance.

The model itself ships inside this package, at
`ecoscope_workflows_ext_wdmodel/data/wd-standard-model-v2.json`: 27 event types
across four categories, with every choice list they reference. It travels in the
wheel rather than being read from a reference instance at run time, so a brand
new organisation can be set up with nothing else reachable, and two runs months
apart produce the same thing.

## Layout

| file | what it is |
|---|---|
| `model.py` | load the shipped model, select types by category, repoint a choice list |
| `provision.py` | work out what is missing on a target, and in what order. No network. |
| `tasks/setup/_plan.py` | the registered task: read an instance, report what would change |

`provision.py` is pure so the ordering rule can be tested without an instance:

    categories -> choice lists -> event types -> schemas

A schema whose `$ref`s point at lists that do not exist yet is accepted by the
API and renders as empty dropdowns. Nothing errors, and nobody finds out until a
ranger opens the form in the field.

## Tests

    pixi run pytest        # from the repository root, offline
