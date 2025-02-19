# Copyright 2020 The TensorFlow Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================

"""Tests for models.object_detection.core.bipartite_matcher."""
import unittest
import numpy as np
import tensorflow.compat.v1 as tf

from models.object_detection.utils import test_case
from models.object_detection.utils import tf_version

if tf_version.is_tf2():
  from models.object_detection.matchers import hungarian_matcher  # pylint: disable=g-import-not-at-top


@unittest.skipIf(tf_version.is_tf1(), 'Skipping TF2.X only test.')
class HungarianBipartiteMatcherTest(test_case.TestCase):

  def test_get_expected_matches_when_all_rows_are_valid(self):
    similarity_matrix = np.array([[0.50, 0.1, 0.8], [0.15, 0.2, 0.3]],
                                 dtype=np.float32)
    valid_rows = np.ones([2], dtype=np.bool)
    expected_match_results = [-1, 1, 0]

    matcher = hungarian_matcher.HungarianBipartiteMatcher()
    match_results_out = matcher.match(similarity_matrix, valid_rows=valid_rows)

    self.assertAllEqual(match_results_out._match_results.numpy(),
                        expected_match_results)

  def test_get_expected_matches_with_all_rows_be_default(self):
    similarity_matrix = np.array([[0.50, 0.1, 0.8], [0.15, 0.2, 0.3]],
                                 dtype=np.float32)
    expected_match_results = [-1, 1, 0]

    matcher = hungarian_matcher.HungarianBipartiteMatcher()
    match_results_out = matcher.match(similarity_matrix)

    self.assertAllEqual(match_results_out._match_results.numpy(),
                        expected_match_results)

  def test_get_no_matches_with_zero_valid_rows(self):
    similarity_matrix = np.array([[0.50, 0.1, 0.8], [0.15, 0.2, 0.3]],
                                 dtype=np.float32)
    valid_rows = np.zeros([2], dtype=np.bool)
    expected_match_results = [-1, -1, -1]

    matcher = hungarian_matcher.HungarianBipartiteMatcher()
    match_results_out = matcher.match(similarity_matrix, valid_rows=valid_rows)

    self.assertAllEqual(match_results_out._match_results.numpy(),
                        expected_match_results)

  def test_get_expected_matches_with_only_one_valid_row(self):
    similarity_matrix = np.array([[0.50, 0.1, 0.8], [0.15, 0.2, 0.3]],
                                 dtype=np.float32)
    valid_rows = np.array([True, False], dtype=np.bool)
    expected_match_results = [-1, -1, 0]

    matcher = hungarian_matcher.HungarianBipartiteMatcher()
    match_results_out = matcher.match(similarity_matrix, valid_rows=valid_rows)

    self.assertAllEqual(match_results_out._match_results.numpy(),
                        expected_match_results)

  def test_get_expected_matches_with_only_one_valid_row_at_bottom(self):
    similarity_matrix = np.array([[0.15, 0.2, 0.3], [0.50, 0.1, 0.8]],
                                 dtype=np.float32)
    valid_rows = np.array([False, True], dtype=np.bool)
    expected_match_results = [-1, -1, 0]

    matcher = hungarian_matcher.HungarianBipartiteMatcher()
    match_results_out = matcher.match(similarity_matrix, valid_rows=valid_rows)

    self.assertAllEqual(match_results_out._match_results.numpy(),
                        expected_match_results)

  def test_get_expected_matches_with_two_valid_rows(self):
    similarity_matrix = np.array([[0.15, 0.2, 0.3], [0.50, 0.1, 0.8],
                                  [0.84, 0.32, 0.2]],
                                 dtype=np.float32)
    valid_rows = np.array([True, False, True], dtype=np.bool)
    expected_match_results = [1, -1, 0]

    matcher = hungarian_matcher.HungarianBipartiteMatcher()
    match_results_out = matcher.match(similarity_matrix, valid_rows=valid_rows)

    self.assertAllEqual(match_results_out._match_results.numpy(),
                        expected_match_results)


if __name__ == '__main__':
  tf.test.main()
