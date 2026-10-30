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

## Before you start

No command line and no EarthRanger admin until after the run. Two things in
Ecoscope Desktop first.

**Add the instance under Data Sources.** The same credentials read the current
configuration and write the new model — there is no second login. On Desktop
1.3.0 and later they are checked when you save the connection, so a wrong
password fails there rather than halfway through.

Use an account with **configuration rights**. Creating categories, choice
lists and event types needs more than a ranger account; a superuser is the
usual answer.

**Add the template**, under Workflow Templates → Add template, from the
repository URL. The first add downloads an environment and takes a few
minutes; later runs are quick.

> When the template changes, **delete and re-add it**. Templates do not update
> in place, and a stale one runs the old code without saying so.

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
until they are activated, in Django admin under `/admin/activity/eventtype/`.

### 4. Grant access

A new category's permissions start with **only the account that ran the
workflow**. Nobody else can see it until you add them, in Django admin under
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

This is exactly what MMNR's copy of the standard model needed.

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

## Publishing a template other people can install

Read this before telling anyone to add the template. As the repository stands
after a normal `pixi run -e compile compile`, **the compiled workflow
installs on the machine that compiled it and nowhere else.**

`pixi run build-release` writes the task package to a local channel under
`/tmp`, and the compiled `pixi.lock` records that path verbatim:

```
- conda: /tmp/ecoscope-workflows-custom/release/artifacts/noarch/ecoscope-workflows-ext-wdmodel-0.0.1-pyh4616a5c_0.conda
```

That is right while iterating — a task change is one compile away rather than
a tag and a publish. It is wrong for distribution: anyone else gets a lock
pointing at a file they do not have, and so do you once `/tmp` is cleared by
a reboot. Nothing warns you. The repository looks complete and the failure
lands on the first person who tries to use it.

### How a release is cut

Three workflows, the same chain every published Ecoscope workflow uses. You
do not tag by hand and there is no API key to hold:

```
VERSION.yaml  →  tag.yml      on PR merge to main: cuts vMAJ.MIN.PATCH
                              and creates the GitHub Release
              →  publish.yml  on that tag: calls _build.yml, then uploads
              →  _build.yml   runs publish/build.sh, uploads the artifact
```

`publish.yml` authenticates to the channel with an **OIDC token**
(`permissions: id-token: write`), so `publish/push.sh` works in CI and fails
locally — tag a release rather than pushing from your machine.

The package version comes from the tag via `hatch-vcs`, which is why
`_build.yml` checks out with `fetch-depth: 0`. **Bump
`ecoscope-workflows-wd-data-model-setup-workflow/VERSION.yaml` in the PR**:
`tag.yml` refuses a tag that already exists, so an unbumped version fails the
PR check rather than silently republishing.

### Then, by hand

**3.** Point the requirement in `spec.yaml` at the remote channel, pinned to
the version just published:

```yaml
  - name: ecoscope-workflows-ext-wdmodel
    version: 0.1.0                                                # not "*"
    channel: https://repo.prefix.dev/ecoscope-workflows-custom/   # not file:///tmp/...
```

An exact version, not `"*"`. The published template should pin what it was
tested against; `"*"` is for local iteration against the `/tmp` channel.

```bash
# 4. recompile. CLEAN_CACHE because channel repodata is cached and a package
#    published two minutes ago is otherwise invisible to the solver.
CLEAN_CACHE=1 MAX_LOCKFILE_VERSION=7 pixi run -e compile compile

# 5. check before committing
grep wdmodel ecoscope-workflows-*-workflow/pixi.lock | head -1
```

An `https://` URL means it will install anywhere. A `/tmp` path means step 3
or 4 did not take, and the template is still local-only.

**6.** Commit the regenerated `pixi.lock` and the compiled package directory.
Desktop installs from that lock, so an uncommitted lock means nobody gets the
fix.

Steps 3–6 stay manual deliberately: a CI job that rewrites `spec.yaml` and
commits a lock is a job that can quietly publish the wrong thing.

They also mean the first release takes **two PRs** — one that merges the code
and cuts the tag, and one that repoints `spec.yaml` at the version that tag
published and commits the recompiled lock. There is no way round that
ordering: the version does not exist until the tag is cut.

To go back to iterating, put the `file:///tmp/...` channel and `version: "*"`
back. Just do not commit a template in that state and call it released.

---

## Development

```bash
pixi run pytest                   # offline, no instance needed
pixi run build-release            # build the task package to the local channel
pixi run -e compile compile       # compile spec.yaml against it
./dev/cleanup.sh                  # list dead files; --delete to remove them
```

The planning and apply logic lives in
`src/ecoscope-workflows-ext-wdmodel/` and is pure — the network is reached only
through a `send` callable, so the ordering rule and the stop-on-failure
behaviour are tested without an instance.

The ordering rule, which must not move:

```
categories -> choice lists -> event types -> schemas
```

A schema whose references point at lists that do not exist yet is accepted by
the API and renders as empty dropdowns.

### One template, two modes

There was briefly a second template for the copy path. It worked, but it made
the operator choose before they could see what either option did. One
template with a `mode` dropdown is the same separation with the choice in a
place where the consequences are visible.

The long comment in `spec.yaml` is the part worth keeping: it records what
Ecoscope Desktop does and does not let a spec control, which is documented
nowhere else. `./dev/cleanup.sh` removes what the abandoned approaches left
behind.

### Which API root

Event types are **v2** and everything else is **v1**:

```
https://host/api/v1.0/activity/events/categories
https://host/api/v1.0/choices
https://host/api/v2.0/activity/eventtypes/
```

erclient is constructed with the v1.0 root and joins relative paths onto it,
so an event-type path has to be routed deliberately — `_rooted_for` in
`tasks/setup/_apply.py` swaps the root for the duration of the call, since
`_post` and `_patch` will not accept a full URL. Getting this wrong produces
a bare `ERClientNotFound('')` with no path in the message, so
`tests/test_api_roots.py` asserts the URLs directly.

Schemas come one type at a time from `activity/eventtypes/<id>/
?include_schema=true`. The list endpoint ignores `include_schema`, and a copy
built on the list alone finds every schema empty and reports nothing to do.

### Where the model came from

`src/ecoscope-workflows-ext-wdmodel/ecoscope_workflows_ext_wdmodel/data/wd-standard-model-v2.json`,
exported from the `trwg_` test build on
`wildlifedynamics.pamdas.org` and reconciled against the live Westgate,
Naibunga and MMNR instances. See `RECONCILIATION.md` for what was taken from
where.
