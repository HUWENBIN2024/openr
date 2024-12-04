python reason/evaluation/evaluate.py \
    --LM aafeb0fc6f22cbf0eaeed126eff8be45b0360a35 \
    --RM 45dc0a3c9ec699b645085c098ed38dc99fba4617 \
    --task_name MATH \
    --temperature 0.7 \
    --max_new_tokens 2048 \
    --num_sequence 1 \
    --tree_max_width 4 \
    --tree_max_depth 50 \
    --save_dir debug \
    --method vanila_mcts \
    --num_worker 32 \
    --controller_addr http://0.0.0.0:28777 \
    --local

# math-shepherd-mistral-7b-prm