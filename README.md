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

27 event types across four categories. Take all four or just the ones an
organisation uses.

| Category | Types |
|---|---|
| **Animal Health** | Animal Carcass, Sick / Injured Animal |
| **Human-Wildlife Conflict** | Crop Damage, Infrastructure Damage, HWC Livestock Predation, Human Death, Human Injury |
| **Field Monitoring** | Wildlife Sighting, Invasive Alien Plant Species, Poisoning, Snares & Traps, Poacher Camp, Poacher Spoor, Gunshot, Arrest, Contact, Recovered Trophy, Theft, Patrol Info, Meeting Report |
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
| **Instance to copy from** | asked for on every run, **ignored** unless the mode says to copy. Point it at the same instance and move on |
| **What this run should do** | *Set up the WD standard model* |
| **Categories** | all four for the full model; deselect the ones the organisation does not use |
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

Pick the source under **Instance to copy from** and **Event types to copy**
fills with that instance's event types, refreshing if you change the source.
Event types rather than categories, because the form can read an instance's
types from the connection and cannot do the same for categories.

### About the second data source

Ecoscope Desktop asks for it on **every** run, including standard-model ones
that never read it. That is the app, not this workflow: connections are
collected in their own wizard step, derived from the spec's connection tasks,
and nothing in the parameter schema reaches that step. Four attempts to make
it optional are recorded in `spec.yaml`.

So on a standard-model run it is cosmetic. Point it at the instance you are
setting up and ignore it — the task does not touch it.

What it is *not* is an implicit switch. The mode dropdown decides, so copy
fields left filled in from an earlier run cannot turn a standard setup into a
copy, and a species list given in copy mode is dropped with a warning rather
than quietly applied. There are tests for both.

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

### What copies, and what doesn't

Only **v2** event types. A v1 form keeps its dropdown options inline instead of
in registered choice lists, so it cannot be recreated as a v2 form without
being rebuilt by hand. Any v1-only type in the selected categories is named in
the results rather than silently skipped.

Choice lists are scoped to what the copied forms actually reference — a source
instance may carry hundreds belonging to other people's work.

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
