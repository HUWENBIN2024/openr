# Licensed under the MIT license.

from .toolkit_for_MATH.latex_answer_check import latex_answer_check as latex_equiv

import os, json, re
from typing import List, Dict, Tuple
from collections import defaultdict
import random
from fuzzywuzzy import fuzz, process

from envs.MATH.parse_utils_qwen import extract_answer as extract_fn, parse_ground_truth, strip_string
from ...MATH.grader import math_equal


class Evaluator:
    def __init__(self) -> None:
        self.answer_marker = "answer is"

    def _is_number(self, s) -> Tuple[bool, str]:
        try:
            res = float(s)
            return True, str(res)
        except:
            pass
        try:
            import unicodedata

            res = unicodedata.numeric(s)
            return True, str(res)
        except:
            pass
        return False, None

    def validate_completion(self, completion: str) -> bool:
        if self.answer_marker.lower() in completion.lower():
            return True

        return False

    def isolate_answer(self, text: str):
        if text is None:
            return None

        assert isinstance(text, str)
        text = text.lower()
        split_ans = text.split(self.answer_marker.lower())
        if len(split_ans) > 1:
            ans = split_ans[-1].replace(":", "").strip()
            extract_ans_temp = ans.split(".\n")[0].strip()
            if len(extract_ans_temp) > 0 and extract_ans_temp[-1] == ".":
                extract_ans = extract_ans_temp[0:-1]
            else:
                extract_ans = extract_ans_temp
            extract_ans = extract_ans.strip().strip("\n")
            return extract_ans
        else:
            return text

    def find_most_confident_answer(self, completions: List[str], prior_weights: List[float] = None):
        """Returns the most confident answer, its completion, its id in the input list, and its confidence."""
        if completions is None or len(completions) == 0:
            return None, None, None, None

        answer2completions = defaultdict(list)
        answer2ids = defaultdict(list)
        for id, c in enumerate(completions):
            try:
                model_answer = self.extract_answer_from_model_completion(c)
                has_existed = False
                for existing_answer in answer2completions.keys():
                    if self.check_answers_equiv(model_answer, existing_answer):
                        assert not has_existed
                        has_existed = True
                        answer2completions[existing_answer].append(c)
                        answer2ids[existing_answer].append(id)
                if not has_existed:
                    answer2completions[model_answer].append(c)
                    answer2ids[model_answer].append(id)
            except:
                pass

        assert len(answer2completions.keys()) > 0, "There are no valid completions."
        if prior_weights is not None:
            assert len(completions) == len(prior_weights)
            completion2count = {}
            for answer, answer_completions in answer2completions.items():
                count = len(answer_completions)
                for answer_completion in answer_completions:
                    completion2count[answer_completion] = count

            completion2score = {}
            for id, (completion, count) in enumerate(completion2count.items()):
                prior_weight = prior_weights[id]
                score = prior_weight * (count / len(completions))
                completion2score[completion] = score

            most_confident_completion = max(completion2score.keys(), key=lambda x: completion2score[x])

            return (
                self.extract_answer_from_model_completion(most_confident_completion),
                most_confident_completion,
                completions.index(most_confident_completion),
                completion2score[most_confident_completion],
            )
        else:
            most_confident_answer = max(answer2completions.keys(), key=lambda x: len(answer2completions[x]))
            assert (
                len(answer2completions[most_confident_answer]) > 0
            ), "There are no completions for the most confident answer."
            confidence = len(answer2completions[most_confident_answer]) / len(completions)
            assert confidence > 0
            return (
                most_confident_answer,
                answer2completions[most_confident_answer][0],
                answer2ids[most_confident_answer][0],
                confidence,
            )

    def stochastic_select_answer(self, completion2score, answer2completions, completions):
        answer2score = {}
        answer_counts = {}
        for completion, score in completion2score.items():
            answer = self.extract_answer_from_model_completion(completion)
            if answer in answer2score:
                answer2score[answer] += score
                answer_counts[answer] += 1
            else:
                answer2score[answer] = score
                answer_counts[answer] = 1

        for answer in answer2score:
            answer2score[answer] /= answer_counts[answer]

        top_answers = sorted(answer2score.items(), key=lambda x: x[1], reverse=True)[:1]
        answers, scores = zip(*top_answers)
        total_score = sum(scores)
        try:
            probabilities = [score / total_score for score in scores]
            selected_answer = random.choices(answers, weights=probabilities, k=1)[0]
        except:
            selected_answer = random.choices(answers, k=1)[0]

        most_confident_completion = answer2completions[selected_answer][0]
        completion_index = completions.index(most_confident_completion)
        confidence = answer2score[selected_answer]

        return selected_answer, most_confident_completion, completion_index, confidence

    def stochastic_calculate_completion_scores(self, prior_weights, answer2completions):
        completion2count = {}
        for answer, comps in answer2completions.items():
            count = len(comps)
            for comp in comps:
                completion2count[comp] = count

        completion2score = {}
        for idx, comp in enumerate(completion2count.keys()):
            weight = prior_weights[idx] if prior_weights is not None else 1
            score = weight * completion2count[comp]
            completion2score[comp] = score
        return completion2score

    def stochastic_select_response(self, completion2score, completions):
        sorted_completions = sorted(completion2score.items(), key=lambda x: x[1], reverse=True)[:1]
        completions, scores = zip(*sorted_completions)
        total_score = sum(scores)
        try:
            probabilities = [score / total_score for score in scores]
            sampled_completion = random.choices(completions, weights=probabilities, k=1)[0]
        except:
            sampled_completion = random.choices(completions, k=1)[0]
        confidence = completion2score[sampled_completion]
        most_confident_answer = self.extract_answer_from_model_completion(sampled_completion)
        id_of_most_confident = completions.index(sampled_completion)
        return most_confident_answer, sampled_completion, id_of_most_confident, confidence

    def stochastic_find_most_confident_answer(
        self,
        completions: List[str],
        prior_weights: List[float] = None,
    ):

        if not completions or len(completions) == 0:
            return None, None, None, None

        answer2completions = defaultdict(list)
        for idx, comp in enumerate(completions):
            try:
                answer = self.extract_answer_from_model_completion(comp)
                answer2completions[answer].append(comp)
            except:
                continue

        if not answer2completions:
            return None, None, None, None

        completion2score = self.stochastic_calculate_completion_scores(prior_weights, answer2completions)

        most_confident_answer, sampled_completion, id_of_most_confident, confidence = self.stochastic_select_response(
            completion2score, completions
        )
        return most_confident_answer, sampled_completion, id_of_most_confident, confidence

    def check_answers_equiv(self, answer_a: str, answer_b: str):
        raise NotImplementedError

    def extract_answer_from_gold_solution(self, solution: str) -> str:
        raise NotImplementedError

    def extract_answer_from_model_completion(self, completion: str) -> str:
        raise NotImplementedError



class MATHEvaluator(Evaluator):
    def __init__(self) -> None:
        super().__init__()

    def check_answers_equiv(self, answer_a: str, answer_b: str):
        if answer_a is None or answer_b is None:
            return False

        if answer_a == "" or answer_b == "":
            return False

        answer_a = answer_a.strip()
        answer_b = answer_b.strip()

        if answer_a.lower() == answer_b.lower():
            return True

        try:
            res = latex_equiv(answer_a, answer_b)
        except Exception as e:
            print(e)
            res = False

        return res

    def extract_answer_from_gold_solution(self, solution: str):
        def remove_boxed(s):
            left = "\\boxed{"
            try:
                assert s[: len(left)] == left
                assert s[-1] == "}"
                return s[len(left) : -1]
            except:
                return None

        def last_boxed_only_string(string):
            idx = string.rfind("\\boxed")
            if idx < 0:
                idx = string.rfind("\\fbox")
                if idx < 0:
                    return None

            i = idx
            right_brace_idx = None
            num_left_braces_open = 0
            while i < len(string):
                if string[i] == "{":
                    num_left_braces_open += 1
                if string[i] == "}":
                    num_left_braces_open -= 1
                    if num_left_braces_open == 0:
                        right_brace_idx = i
                        break
                i += 1

            if right_brace_idx == None:
                retval = None
            else:
                retval = string[idx : right_brace_idx + 1]

            return retval

        return remove_boxed(last_boxed_only_string(solution))

    def extract_answer_from_model_completion(self, completion):
        answer_split = self.isolate_answer(completion)
        return answer_split



class QwenMATHEvaluator(Evaluator):
    def __init__(self) -> None:
        super().__init__()

    def isolate_answer(self, text: str):
        if text is None:
            return None

        use_last_number = True
        data_name = 'math'

        pred_str = text.replace("\u043a\u0438", "")
        if "answer is" in pred_str and "$. I hope" in pred_str:
            # minerva_math
            tmp = pred_str.split("answer is", 1)[1]
            pred = tmp.split("$. I hope", 1)[0].strip()
        elif "boxed" in pred_str:
            ans = pred_str.split("boxed")[-1]
            if len(ans) == 0:
                return ""
            elif ans[0] == "{":
                stack = 1
                a = ""
                for c in ans[1:]:
                    if c == "{":
                        stack += 1
                        a += c
                    elif c == "}":
                        stack -= 1
                        if stack == 0:
                            break
                        a += c
                    else:
                        a += c
            else:
                a = ans.split("$")[0].strip()
            pred = a
        elif "he answer is" in pred_str:
            pred = pred_str.split("he answer is")[-1].strip()
        elif "final answer is" in pred_str:
            pred = pred_str.split("final answer is")[-1].strip()
        elif "答案是" in pred_str:
            # Handle Chinese few-shot multiple choice problem answer extraction
            pred = pred_str.split("答案是")[1].strip().split("\n\n")[0].strip()
        else:  # use the last number
            if use_last_number:
                pattern = "-?\d*\.?\d+"
                pred = re.findall(pattern, pred_str.replace(",", ""))
                if len(pred) >= 1:
                    pred = pred[-1]
                else:
                    pred = ""
            else:
                pred = ""

        # multiple line
        # pred = pred.split("\n")[0]
        pred = re.sub(r"\n\s*", "", pred)
        if pred != "" and pred[0] == ":":
            pred = pred[1:]
        if pred != "" and pred[-1] == ".":
            pred = pred[:-1]
        if pred != "" and pred[-1] == "/":
            pred = pred[:-1]
        pred = strip_string(pred, skip_unit=data_name in ["carp_en", "minerva_math"])
        return pred



    def extract_answer_from_model_completion(self, completion):
        answer_split = self.isolate_answer(completion)
        return answer_split


    def check_answers_equiv(self, answer_a: str, answer_b: str):

        if answer_a is None or answer_b is None:
            return False

        if answer_a == "" or answer_b == "":
            return False

        answer_a = answer_a.strip()
        answer_b = answer_b.strip()

        if answer_a.lower() == answer_b.lower():
            return True

        if math_equal(answer_a, answer_b):
            return True

        try:
            res = latex_equiv(answer_a, answer_b)
        except Exception as e:
            print(e)
            res = False

        return res