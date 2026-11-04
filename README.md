# WD Data Model Setup

Sets up the Wildlife Dynamics standard conservancy data model on any
EarthRanger instance: the categories, the choice lists, the event types and
their forms, in one run.

Doing this by hand is 27 event types per organisation, each a form built field
by field, and every one of them a chance to point a field at the wrong choice
list. A mistyped reference does not error — the form renders with an empty
dropdown, and nobody finds out until a ranger is standing over a carcass.

---

## What it creates

27 event types across three categories. Take all three or just the ones an
organisation uses — Rangeland Monitoring is the one most sites leave out.

| Category | Types |
|---|---|
| **Animal Health** | Animal Carcass, Sick / Injured Animal |
| **Field Monitoring** | Wildlife Sighting, Crop Damage, Infrastructure Damage, HWC Livestock Predation, Human Death, Human Injury, Invasive Alien Plant Species, Poisoning, Snares & Traps, Poacher Camp, Poacher Spoor, Gunshot, Arrest, Contact, Recovered Trophy, Theft, Patrol Info, Meeting Report |
| **Rangeland Monitoring** | Rangelands Meeting, Rangeland Rehabilitation, Encroachment, Livestock Movement, Livestock Household Survey Questionnaire, Grazing Meeting, Monthly Grazing Block Count |

Plus the choice lists those forms need — 125 of them, 1,165 options — created
**before** the forms that reference them.

The model travels inside the workflow. No reference instance has to be
reachable, and two runs months apart produce the same thing.

---

## How to run

**Add the instance under Data Sources.** The same credentials read the current
configuration and write the new model — there is no second login. On Desktop
1.3.0 and later, they are checked when you save the connection, so a wrong
password fails there rather than halfway through.

Use an account with **configuration rights**. Creating categories, choice
lists and event types needs more than a ranger account; a superuser is the
usual answer.

**Add the template**, under Workflow Templates → Add template, from the
repository URL. The first add downloads an environment and takes a few
minutes; later runs are quick.

---

## Running it

Open the template and **Configure New Workflow**.

| Field | What to put |
|---|---|
| **Workflow Name** | something you will recognise in the run list — `Mara — dry run 1` |
| **EarthRanger instance to set up** | the Data Source from above. The only instance written to |
| **What this run should do** | *Set up the WD standard model*. The copy fields, including the source instance, are not shown at all |
| **Categories** | all three for the full model; deselect the ones the organisation does not use |
| **Species** | both fields empty unless the instance has a curated list, or you are supplying a CSV |
| **Activate the event types immediately** | leave off on an instance where people are collecting data today |
| **Dry run** | **leave ticked** |
| **Advanced → Event type prefix** | `trial_` for a rehearsal; empty for the real build |

### 1. Dry run first

Leave **Dry run** on and submit. Nothing is written. The table lists every
intended change, in the order it would happen:

```
WHAT         NAME                     VALUE                  STATE    DETAIL
category     Animal Health            animal_health          planned  create
choice       injuredanimal_symptom…   injuredanimal_symptom… planned  5 rows
event type   Animal Carcass           animal_carcass         planned  33 fields
schema       Animal Carcass           animal_carcass         planned  with the event type
```

A full model on an empty instance is about 180 rows: 4 categories, ~118
choice lists, 27 event types, 27 schemas. Anything already on the instance is
skipped, so a short table means most of the model is there.

Then read the `warning` rows at the bottom. Those are the ones that matter —
see *Read the collision warnings* below.

### 2. Turn Dry run off and submit again

Same settings, Dry run off. The table comes back with `created` instead of
`planned`.

If a write fails, the run stops there and says so in the first warning row.
Nothing is rolled back; fix the cause and run again.

### 3. Activate the event types

Unless you ticked **Activate the event types immediately**, they were created
inactive — and a category with no active event types is invisible in
EarthRanger **to everyone, superusers included**. You will see nothing at all
until they are activated, in admin under `/admin/activity/eventtype/`.

### 4. Grant access

A new category's permissions start with **only the account that ran the
workflow**. Nobody else can see it until you add them, in admin under
`/admin/accounts/permissionset/`.

Each category has **two** permission sets, and you need both:

```
View <Category> Event Permissions              the forms
View <Category> Event Geographic Permissions   what ER Mobile reads
```

Populating only the first is the commonest mistake. Everything looks right on
the web and the category never appears on anyone's phone.

---

## Copying a model from another instance

Set **What this run should do** to *Copy event types from another instance*.
That dropdown, and nothing else, decides which half of the form is read.

Pick the source under **Instance to copy from**, then type the source's
category values into **Categories to copy** — one per row. Every v2 event
type in them comes across, with its choice lists. Categories rather than
individual types because a whole model is two or three values rather than
twenty-seven, and there is no dropdown to pick from — see *Why there is no
dropdown* below.

### The source instance

**Instance to copy from** is a field of the copy branch itself, so a standard
run does not render it at all.

Getting there took five attempts. A second `set_er_connection` task puts the
picker in Desktop's Data Sources step, which demands a selection on every run;
`required: []` and a `{"name": ""}` default both left it mandatory; an RJSF
`dependencies` toggle hid it and broke other things; and as a top-level
parameter of the Set up task it rendered correctly but showed on every run,
copy or not.

The generated `metadata.get_data_connection_property_names()` walks two
levels of `params.json` and so cannot see this one, but that is not what
registers it. Desktop's form layer runs its own scan that recurses through
`$ref`, `properties`, `items` and `anyOf`/`oneOf`, and that one finds it.

### Why there is no dropdown

**Categories to copy** is a list you type values into, because Ecoscope
Desktop cannot run a source-options lookup against a connection nested inside
a Union branch.

Three experiments, one variable each:

| `depends_on` | form builds | list loads |
|---|---|---|
| `$defs.CopyFromInstance…source.properties.name` | yes | **no** |
| `properties.setup…what.properties.source…name` | **no** | — |
| `properties.er_target…data_source.properties.name` | yes | yes |

Row 1 resolves — the form builds, so the alias is right — and the lookup
still fails. Row 2 does not resolve at all: a node inside an `anyOf` answers
only to its `$defs`-rooted alias, not a `properties`-rooted one. Row 3 is the
same resolver on the same field inside the same branch, reading a *top-level*
connection, and it works.

So a resolver **field** inside a Union branch is fine; a **connection**
inside one cannot feed a lookup. The hidden picker and the dropdown are
mutually exclusive, and the hidden picker won — copying is the rarer path and
is always deliberate, while every run otherwise pays for a connection field
it does not use.

Typing categories rather than event types is the other half of that. The
original reason for selecting types was that the form could populate a list
of an instance's *types* from a connection and could not do the same for
categories. With no dropdown either way, that reason is gone, and a category
is two or three values instead of twenty-seven.

Type the **values**, not display names — `field_monitoring`, not *Field
Monitoring*. A dry run checks each one against the source and names the near
misses for anything it cannot find, which is why you run one first.

If a category holds a type you do not want, copy the category and deactivate
that type afterwards. There is no way to take a subset.

### Where the copied types land

By default each type keeps the category it has on the source, and that category
is created on the target if it isn't there — `rhino_sighting` from Rhino
Monitoring arrives in a Rhino Monitoring category.

**Put them all in this category** overrides that and files everything under
one category instead. This is the Westgate → MMNR move: Westgate's standard-model
types sit in `field_monitoring_2`, a name it carries only because of a
permissions collision in its own history, and they were written into MMNR as
plain `field_monitoring`. Inheriting would have carried that accident into
every instance built from it.

Leave it blank to inherit; set it to re-file.

### If a type cannot be read from the source

Schemas are read one at a time from the source's detail route, and an
instance that refuses one gets a warning row rather than a failed run:

```
warning  event type 'wildlife_sighting' could not be read from the source and
         was skipped: activity/eventtypes/abc-123/ -> ERClientNotFound;
         activity/eventtypes/abc-123 -> ERClientNotFound. The id used was
         'abc-123', taken from the event type list.
```

Both spellings of the route are tried, with and without the trailing slash,
because instances disagree and a miss is a hard 404 rather than an empty
body. The warning names the id so it can be checked against the source's
admin directly.

If **every** type fails this way the run stops, because there is nothing to
copy — and the error carries the warnings, so the URL and the error class are
in front of you.

### What copies, and what doesn't

Only **v2** event types. A v1 form keeps its dropdown options inline instead of
in registered choice lists, so it cannot be recreated as a v2 form without
being rebuilt by hand. Any v1-only type in the selected categories is named in
the results rather than silently skipped.

Choice lists are scoped to what the copied forms actually reference — a source
instance may carry hundreds belonging to other people's work.

### Species on a copy run

A copied form points at whatever the source instance called its species list.
**Species list for the copied forms** decides what happens to that:

| Setting | What it does |
|---|---|
| `source` | Default. Keeps the source's list exactly as it is. |
| `standard` | Repoints the copied forms at the WD standard 66-entry list. |
| `csv` | Repoints them at a list built from your own CSV — same format as the standard-model one below. |

Repointing moves **both halves**: the rows are renamed to `species` and every
`$ref` in every copied schema moves with them. Renaming one without the other
is the bug that left MMNR's Left Tusk section unreachable.

**Only the general species list moves.** A source may well have
`livestock_species`, `species_of_vulture_at_carcass` and
`alien_plant_species` alongside it, and merging those onto one list would put
elephants in a livestock dropdown. Lists are matched on the name — the source
chose those names, not us — so the match is a heuristic and acts like one:
every list it repoints and every "species" list it declines comes back as a
row in the results. Read them on the dry run.

Two more things it will tell you rather than do quietly:

- if the copied forms reference **no** general species list, nothing is
  repointed and the lists it did see are named;
- if the source had **several** general species lists, they are merged onto
  one and the merge is called out — a form rule keyed on a value only one of
  them carried will stop firing.

The other choice lists are unaffected; they come from the source as before,
with **Prefix for clashing choice lists** below for collisions.

### Read the collision warnings

This is the one that bites. A choice list already on the target is **skipped,
not overwritten** — overwriting somebody else's vocabulary would be worse. But
it means the copied form binds to the *target's* version of that list. If the
two have different options, a form rule keyed on a value the target lacks
**silently never fires**, and the section it controls never appears.

The dry run compares them and says so:

```
WHAT     DETAIL
warning  choice list 'tusk_status' already exists on the target with different
         options and will NOT be overwritten. Missing there: ['left_tusk_present',
         ...]. Any form rule keyed on a missing value will silently never fire.
```

### Letting it rename them for you

Set **Prefix for clashing choice lists** — `fm_`, say — and any list that
clashes is brought in under a new name:

```
tusk_status   -> fm_tusk_status     different options, renamed
action_taken  -> fm_action_taken    different options, renamed
species                             identical, shared as-is
```

**Only clashing lists are renamed.** One whose options already match is shared.
Renaming everything would give each instance a private vocabulary and defeat
the comparability the standard model exists for.

Both halves move together — the rows *and* every `$ref` in every schema.
Renaming the rows alone would leave the form bound to whatever carries the old
name on the target, which is the bug the rename was meant to avoid, only harder
to see.

A rename is **refused rather than forced** if the new name wouldn't work:

- the prefixed name is already taken on the target
- it would exceed the 40-character limit on `choices.field`
- the prefix isn't lowercase letters, digits and underscores

In the first two cases the list is left alone and the warning says why, because
a half-applied rename — schema pointing one way, rows written another — is
worse than none.

Leave the prefix empty and clashing lists are skipped instead, with the warning
above.

---

## The form

### Categories

Pick any combination. Choice lists are scoped to what you select — an
organisation taking only Animal Health does not inherit the rangeland
vocabulary.

### Species list

Three ways, in order of preference:

**Leave both blank** — creates the standard 66-entry list.

**Name a list the instance already has** — every species field is repointed at
it and no second list is created. Use this when a site already has a curated
list; MMNR's is `wildlifesightingrep_species`. Two species lists on one
instance is how a model starts to fork.

**Supply a CSV** — see below.

### Activate the event types immediately

Off by default. A category with **no active event types is invisible in
EarthRanger to everyone, superusers included** — so with this off you will see
nothing until you activate them in Django admin.

Leave it off on an instance where people are collecting data today. Turn it on
for a new or quiet instance, so you can see what you just made.

### Advanced

**Event type prefix** — e.g. `trw_` for a rehearsal. Event type values are
unique per instance, so an unprefixed test build takes the name the real one
needs later and you cannot have it back.

**Replace schemas that already exist** — off by default. On, it rewrites the
form of any event type that is already there, which may be one somebody else
built.

---

## The species CSV

A header row and two required columns, with an optional third:

```csv
value,display,ordernum
grevys_zebra,Grevy's Zebra,10
reticulated_giraffe,Reticulated Giraffe,20
beisa_oryx,Beisa Oryx,30
```

| Column | Required | What it is |
|---|---|---|
| `value` | yes | What is stored on every record. Lowercase letters, digits and underscores only. **This can never be changed once data exists** — the form's conditionals match on it, and every saved record carries it. |
| `display` | yes | What the ranger sees in the dropdown. Free text, apostrophes and spaces fine. |
| `ordernum` | no | Order in the dropdown. Leave it out for alphabetical. |

The whole file is checked before anything is written — a missing column, an
empty cell, a duplicate value, a value with spaces or capitals, a non-numeric
`ordernum`. Failures name the line number. A list half created because line 80
was malformed would have to be found and cleaned up by hand, since choice rows
have no transaction around them.

The CSV replaces the contents of the standard `species` list, keeping its name,
so no form has to be re-pointed.

---

## If something goes wrong

**The run stops at the first failure.** It does not carry on, because the
report would then say "created" for things whose dependencies never landed.
Nothing is rolled back. Fix the cause and run again — the plan is recomputed
against what is actually on the instance, so completed work is skipped and the
run resumes where it stopped.

**Re-running is safe.** Everything already present is skipped. A re-run after a
partial failure finishes the job rather than colliding with itself.

**There is no undo.** A category cannot be safely deleted — toggling its active
flag throws a duplicate-key error on `auth_permission` and has left categories
permanently broken. An event type that has taken a single record cannot be
removed. This is why Dry run is on by default.

**Event type values are unique per instance.** An unprefixed rehearsal takes
the name the real build needs later and you cannot have it back. Use
`trial_` or similar for anything you intend to throw away — and note the
prefix applies to event types only, not to choice lists, so a prefixed
rehearsal still reports the same collision warnings a real run would.

---
