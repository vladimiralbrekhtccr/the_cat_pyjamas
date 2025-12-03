
PROVIDER="local" #  [local, gemini]
GROUP_PATH="evaluation_pipeline_test" #

python src/evaluation/run_evaluation.py \
    --provider $PROVIDER \
    --group_path $GROUP_PATH
