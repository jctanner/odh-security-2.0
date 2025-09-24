# Getting Started

## Prepare your machine to use this tool

Install https://cli.github.com/ as the code will use that for github + git operations.

```
git clone https://github.com/jctanner/odh-security-2.0
cd odh-security-2.0
virtualenv venv
source venv/bin/activate
pip install -r requirements.txt
```

### add your github API token to a secrets file
```
echo $TOKEN > .github_token
```

## Change settings in config.yaml

Take a look at config.yaml and make yourself familiar with the structure. Pay close attention to the `github` section as that defines where all your forks live and what branches to use.

The `additional_repositories` key allows you to define additonal repos to clone that aren't defined by the operator's `get_all_manifests.sh` script. This also allows you to override where specific repos (like the operator) would get cloned from, so if you wanted to use the upstream repo or someone else's fork, you could define that here.

**IMPORTANT** if you plan to build and deploy images, this tool is going to use jtanner's personal/public container registry and will inevitably collide with other peoples image, if you do not change the value for the `namespace` field in the `registry` section of the config. It's probably easiest to simply change it from `odh-security-2.0` to your username.

## Get all the source repos cloned to your machine

### create all the clones

This will clone every repo necessary to make a complete dev stack for ODH. If the repo doesn't exist in the org specified by config.yaml, it will be forked from the repo as defined in `get_all_manifests.sh`

```
./tool.py clone-forks
```

### copy manifests into the operator repo

This is an important step to follow if you want to use the manifests from your adjacent component checkouts. If you skip this, you'll end up with the default manifests as defined by the `get_all_manifests.sh` script.

```
./tool.py workflow --name=manifests --exec
```

## OPTION A: run the operator locally

### do all the pre-deploy stuff
```
./tool.py workflow --name=pre-deploy --exec
```

### run the operator locally
```
cd src/opendatahub-operator
make run-nowebhook
```

## OPTION B: make an operator image and deploy it

**NOTE**: this currently only builds & deploys the opendatahub-operator. Building the component images and injecting their uirs into the opendatahub-operator's manifests is a TBD. In the future this will work more like konflux in that it should build all dependencies first, then build the odh operator last to include all the deps.

### build the image

```
./tool.py workflow --name=image_build --exec
```

### push the image
```
./tool.py workflow --name=image_push --exec
```

### deploy the image
```
./tool.py workflow --name=image_deploy --exec
```

## Create your dsci and dsc

### create the dsci
```
oc apply -f test.configs/dsci.yaml
```

Wait for status to be "ready" ...

```
watch oc get dsci
```

### create the dsc
```
oc apply -f test.configs/dsc.yaml
```

Wait for the status to be "ready" ...

```
watch oc get dsc
```
