# Getting Setup
## Ensure you are running the anaconda `4.5.x +`

## Creating the env
```
conda env create -f loadinsight-environment.yml
```

## Updating the env after adding new packages
```
conda env update -f loadinsight-environment.yml
```

## Starting the env
```
conda activate venv_loadinsight
```

## Stopping the env
```
conda deactivate
```

# Running LCTK

```
python -d init.py  # runs with DEBUG=True
```

# Executing tests locally
```
# make sure you venv is active
python -m unittest
```