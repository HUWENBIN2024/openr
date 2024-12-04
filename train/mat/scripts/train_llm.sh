#!/bin/sh

CUDA_VISIBLE_DEVICES=0 python -u train_math.py --seed 10 \
                        --dataset_name "prealgebra" \
                        --dataset_path "../envs/math/data/math_500.jsonl" \
                        --model_name_or_path "Qwen/Qwen2.5-Math-0.5B-Instruct" \
                        --prm_type "MS" \
                        --prm_model_name_or_path "peiyi9979/math-shepherd-mistral-7b-prm" \
                        --prm_checkpoint_path "ck_path" \
                        --algorithm_name "APPO" \
                        --experiment_name "ms_single" \
                        --num_mini_batch 4 \
                        --ppo_epoch 1

