# Copyright 2022 The TensorFlow Authors. All Rights Reserved.
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

"""Tests for autoaugment."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import random
from absl.testing import parameterized

import tensorflow as tf

from models.official.vision.beta.ops import augment


def get_dtype_test_cases():
  return [
      ('uint8', tf.uint8),
      ('int32', tf.int32),
      ('float16', tf.float16),
      ('float32', tf.float32),
  ]


@parameterized.named_parameters(get_dtype_test_cases())
class TransformsTest(parameterized.TestCase, tf.test.TestCase):
  """Basic tests for fundamental transformations."""

  def test_to_from_4d(self, dtype):
    for shape in [(10, 10), (10, 10, 10), (10, 10, 10, 10)]:
      original_ndims = len(shape)
      image = tf.zeros(shape, dtype=dtype)
      image_4d = augment.to_4d(image)
      self.assertEqual(4, tf.rank(image_4d))
      self.assertAllEqual(image, augment.from_4d(image_4d, original_ndims))

  def test_transform(self, dtype):
    image = tf.constant([[1, 2], [3, 4]], dtype=dtype)
    self.assertAllEqual(
        augment.transform(image, transforms=[1] * 8), [[4, 4], [4, 4]])

  def test_translate(self, dtype):
    image = tf.constant(
        [[1, 0, 1, 0], [0, 1, 0, 1], [1, 0, 1, 0], [0, 1, 0, 1]], dtype=dtype)
    translations = [-1, -1]
    translated = augment.translate(image=image, translations=translations)
    expected = [[1, 0, 1, 1], [0, 1, 0, 0], [1, 0, 1, 1], [1, 0, 1, 1]]
    self.assertAllEqual(translated, expected)

  def test_translate_shapes(self, dtype):
    translation = [0, 0]
    for shape in [(3, 3), (5, 5), (224, 224, 3)]:
      image = tf.zeros(shape, dtype=dtype)
      self.assertAllEqual(image, augment.translate(image, translation))

  def test_translate_invalid_translation(self, dtype):
    image = tf.zeros((1, 1), dtype=dtype)
    invalid_translation = [[[1, 1]]]
    with self.assertRaisesRegex(TypeError, 'rank 1 or 2'):
      _ = augment.translate(image, invalid_translation)

  def test_rotate(self, dtype):
    image = tf.reshape(tf.cast(tf.range(9), dtype), (3, 3))
    rotation = 90.
    transformed = augment.rotate(image=image, degrees=rotation)
    expected = [[2, 5, 8], [1, 4, 7], [0, 3, 6]]
    self.assertAllEqual(transformed, expected)

  def test_rotate_shapes(self, dtype):
    degrees = 0.
    for shape in [(3, 3), (5, 5), (224, 224, 3)]:
      image = tf.zeros(shape, dtype=dtype)
      self.assertAllEqual(image, augment.rotate(image, degrees))


class AutoaugmentTest(tf.test.TestCase, parameterized.TestCase):

  AVAILABLE_POLICIES = [
      'v0',
      'test',
      'simple',
      'reduced_cifar10',
      'svhn',
      'reduced_imagenet',
      'detection_v0',
  ]

  def test_autoaugment(self):
    """Smoke test to be sure there are no syntax errors."""
    image = tf.zeros((224, 224, 3), dtype=tf.uint8)

    for policy in self.AVAILABLE_POLICIES:
      augmenter = augment.AutoAugment(augmentation_name=policy)
      aug_image = augmenter.distort(image)

      self.assertEqual((224, 224, 3), aug_image.shape)

  def test_autoaugment_with_bboxes(self):
    """Smoke test to be sure there are no syntax errors with bboxes."""
    image = tf.zeros((224, 224, 3), dtype=tf.uint8)
    bboxes = tf.ones((2, 4), dtype=tf.float32)

    for policy in self.AVAILABLE_POLICIES:
      augmenter = augment.AutoAugment(augmentation_name=policy)
      aug_image, aug_bboxes = augmenter.distort_with_boxes(image, bboxes)

      self.assertEqual((224, 224, 3), aug_image.shape)
      self.assertEqual((2, 4), aug_bboxes.shape)

  def test_randaug(self):
    """Smoke test to be sure there are no syntax errors."""
    image = tf.zeros((224, 224, 3), dtype=tf.uint8)

    augmenter = augment.RandAugment()
    aug_image = augmenter.distort(image)

    self.assertEqual((224, 224, 3), aug_image.shape)

  def test_randaug_with_bboxes(self):
    """Smoke test to be sure there are no syntax errors with bboxes."""
    image = tf.zeros((224, 224, 3), dtype=tf.uint8)
    bboxes = tf.ones((2, 4), dtype=tf.float32)

    augmenter = augment.RandAugment()
    aug_image, aug_bboxes = augmenter.distort_with_boxes(image, bboxes)

    self.assertEqual((224, 224, 3), aug_image.shape)
    self.assertEqual((2, 4), aug_bboxes.shape)

  def test_randaug_build_for_detection(self):
    """Smoke test to be sure there are no syntax errors built for detection."""
    image = tf.zeros((224, 224, 3), dtype=tf.uint8)
    bboxes = tf.ones((2, 4), dtype=tf.float32)

    augmenter = augment.RandAugment.build_for_detection()
    self.assertCountEqual(augmenter.available_ops, [
        'AutoContrast', 'Equalize', 'Invert', 'Posterize', 'Solarize', 'Color',
        'Contrast', 'Brightness', 'Sharpness', 'Cutout', 'SolarizeAdd',
        'Rotate_BBox', 'ShearX_BBox', 'ShearY_BBox', 'TranslateX_BBox',
        'TranslateY_BBox'
    ])

    aug_image, aug_bboxes = augmenter.distort_with_boxes(image, bboxes)
    self.assertEqual((224, 224, 3), aug_image.shape)
    self.assertEqual((2, 4), aug_bboxes.shape)

  def test_all_policy_ops(self):
    """Smoke test to be sure all augmentation functions can execute."""

    prob = 1
    magnitude = 10
    replace_value = [128] * 3
    cutout_const = 100
    translate_const = 250

    image = tf.ones((224, 224, 3), dtype=tf.uint8)
    bboxes = None

    for op_name in augment.NAME_TO_FUNC.keys() - augment.REQUIRE_BOXES_FUNCS:
      func, _, args = augment._parse_policy_info(op_name, prob, magnitude,
                                                 replace_value, cutout_const,
                                                 translate_const)
      image, bboxes = func(image, bboxes, *args)

    self.assertEqual((224, 224, 3), image.shape)
    self.assertIsNone(bboxes)

  def test_all_policy_ops_with_bboxes(self):
    """Smoke test to be sure all augmentation functions can execute."""

    prob = 1
    magnitude = 10
    replace_value = [128] * 3
    cutout_const = 100
    translate_const = 250

    image = tf.ones((224, 224, 3), dtype=tf.uint8)
    bboxes = tf.ones((2, 4), dtype=tf.float32)

    for op_name in augment.NAME_TO_FUNC:
      func, _, args = augment._parse_policy_info(op_name, prob, magnitude,
                                                 replace_value, cutout_const,
                                                 translate_const)
      image, bboxes = func(image, bboxes, *args)

    self.assertEqual((224, 224, 3), image.shape)
    self.assertEqual((2, 4), bboxes.shape)

  def test_autoaugment_video(self):
    """Smoke test with video to be sure there are no syntax errors."""
    image = tf.zeros((2, 224, 224, 3), dtype=tf.uint8)

    for policy in self.AVAILABLE_POLICIES:
      augmenter = augment.AutoAugment(augmentation_name=policy)
      aug_image = augmenter.distort(image)

      self.assertEqual((2, 224, 224, 3), aug_image.shape)

  def test_autoaugment_video_with_boxes(self):
    """Smoke test with video to be sure there are no syntax errors."""
    image = tf.zeros((2, 224, 224, 3), dtype=tf.uint8)
    bboxes = tf.ones((2, 2, 4), dtype=tf.float32)

    for policy in self.AVAILABLE_POLICIES:
      augmenter = augment.AutoAugment(augmentation_name=policy)
      aug_image, aug_bboxes = augmenter.distort_with_boxes(image, bboxes)

      self.assertEqual((2, 224, 224, 3), aug_image.shape)
      self.assertEqual((2, 2, 4), aug_bboxes.shape)

  def test_randaug_video(self):
    """Smoke test with video to be sure there are no syntax errors."""
    image = tf.zeros((2, 224, 224, 3), dtype=tf.uint8)

    augmenter = augment.RandAugment()
    aug_image = augmenter.distort(image)

    self.assertEqual((2, 224, 224, 3), aug_image.shape)

  def test_all_policy_ops_video(self):
    """Smoke test to be sure all video augmentation functions can execute."""

    prob = 1
    magnitude = 10
    replace_value = [128] * 3
    cutout_const = 100
    translate_const = 250

    image = tf.ones((2, 224, 224, 3), dtype=tf.uint8)
    bboxes = None

    for op_name in augment.NAME_TO_FUNC.keys() - augment.REQUIRE_BOXES_FUNCS:
      func, _, args = augment._parse_policy_info(op_name, prob, magnitude,
                                                 replace_value, cutout_const,
                                                 translate_const)
      image, bboxes = func(image, bboxes, *args)

    self.assertEqual((2, 224, 224, 3), image.shape)
    self.assertIsNone(bboxes)

  def test_all_policy_ops_video_with_bboxes(self):
    """Smoke test to be sure all video augmentation functions can execute."""

    prob = 1
    magnitude = 10
    replace_value = [128] * 3
    cutout_const = 100
    translate_const = 250

    image = tf.ones((2, 224, 224, 3), dtype=tf.uint8)
    bboxes = tf.ones((2, 2, 4), dtype=tf.float32)

    for op_name in augment.NAME_TO_FUNC:
      func, _, args = augment._parse_policy_info(op_name, prob, magnitude,
                                                 replace_value, cutout_const,
                                                 translate_const)
      if op_name in {
          'Rotate_BBox',
          'ShearX_BBox',
          'ShearY_BBox',
          'TranslateX_BBox',
          'TranslateY_BBox',
          'TranslateY_Only_BBoxes',
      }:
        with self.assertRaises(ValueError):
          func(image, bboxes, *args)
      else:
        image, bboxes = func(image, bboxes, *args)

    self.assertEqual((2, 224, 224, 3), image.shape)
    self.assertEqual((2, 2, 4), bboxes.shape)

  def _generate_test_policy(self):
    """Generate a test policy at random."""
    op_list = list(augment.NAME_TO_FUNC.keys())
    size = 6
    prob = [round(random.uniform(0., 1.), 1) for _ in range(size)]
    mag = [round(random.uniform(0, 10)) for _ in range(size)]
    policy = []
    for i in range(0, size, 2):
      policy.append([(op_list[i], prob[i], mag[i]),
                     (op_list[i + 1], prob[i + 1], mag[i + 1])])
    return policy

  def test_custom_policy(self):
    """Test autoaugment with a custom policy."""
    image = tf.zeros((224, 224, 3), dtype=tf.uint8)
    augmenter = augment.AutoAugment(policies=self._generate_test_policy())
    aug_image = augmenter.distort(image)

    self.assertEqual((224, 224, 3), aug_image.shape)

  @parameterized.named_parameters(
      {'testcase_name': '_OutOfRangeProb',
       'sub_policy': ('Equalize', 1.1, 3), 'value': '1.1'},
      {'testcase_name': '_OutOfRangeMag',
       'sub_policy': ('Equalize', 0.9, 11), 'value': '11'},
  )
  def test_invalid_custom_sub_policy(self, sub_policy, value):
    """Test autoaugment with out-of-range values in the custom policy."""
    image = tf.zeros((224, 224, 3), dtype=tf.uint8)
    policy = self._generate_test_policy()
    policy[0][0] = sub_policy
    augmenter = augment.AutoAugment(policies=policy)

    with self.assertRaisesRegex(
        tf.errors.InvalidArgumentError,
        r'Expected \'tf.Tensor\(False, shape=\(\), dtype=bool\)\' to be true. '
        r'Summarized data: ({})'.format(value)):
      augmenter.distort(image)

  def test_invalid_custom_policy_ndim(self):
    """Test autoaugment with wrong dimension in the custom policy."""
    policy = [[('Equalize', 0.8, 1), ('Shear', 0.8, 4)],
              [('TranslateY', 0.6, 3), ('Rotate', 0.9, 3)]]
    policy = [[policy]]

    with self.assertRaisesRegex(
        ValueError,
        r'Expected \(:, :, 3\) but got \(1, 1, 2, 2, 3\).'):
      augment.AutoAugment(policies=policy)

  def test_invalid_custom_policy_shape(self):
    """Test autoaugment with wrong shape in the custom policy."""
    policy = [[('Equalize', 0.8, 1, 1), ('Shear', 0.8, 4, 1)],
              [('TranslateY', 0.6, 3, 1), ('Rotate', 0.9, 3, 1)]]

    with self.assertRaisesRegex(
        ValueError,
        r'Expected \(:, :, 3\) but got \(2, 2, 4\)'):
      augment.AutoAugment(policies=policy)

  def test_invalid_custom_policy_key(self):
    """Test autoaugment with invalid key in the custom policy."""
    image = tf.zeros((224, 224, 3), dtype=tf.uint8)
    policy = [[('AAAAA', 0.8, 1), ('Shear', 0.8, 4)],
              [('TranslateY', 0.6, 3), ('Rotate', 0.9, 3)]]
    augmenter = augment.AutoAugment(policies=policy)

    with self.assertRaisesRegex(KeyError, '\'AAAAA\''):
      augmenter.distort(image)


class RandomErasingTest(tf.test.TestCase, parameterized.TestCase):

  def test_random_erase_replaces_some_pixels(self):
    image = tf.zeros((224, 224, 3), dtype=tf.float32)
    augmenter = augment.RandomErasing(probability=1., max_count=10)

    aug_image = augmenter.distort(image)

    self.assertEqual((224, 224, 3), aug_image.shape)
    self.assertNotEqual(0, tf.reduce_max(aug_image))


class MixupAndCutmixTest(tf.test.TestCase, parameterized.TestCase):

  def test_mixup_and_cutmix_smoothes_labels(self):
    batch_size = 12
    num_classes = 1000
    label_smoothing = 0.1

    images = tf.random.normal((batch_size, 224, 224, 3), dtype=tf.float32)
    labels = tf.range(batch_size)
    augmenter = augment.MixupAndCutmix(
        num_classes=num_classes, label_smoothing=label_smoothing)

    aug_images, aug_labels = augmenter.distort(images, labels)

    self.assertEqual(images.shape, aug_images.shape)
    self.assertEqual(images.dtype, aug_images.dtype)
    self.assertEqual([batch_size, num_classes], aug_labels.shape)
    self.assertAllLessEqual(aug_labels, 1. - label_smoothing +
                            2. / num_classes)  # With tolerance
    self.assertAllGreaterEqual(aug_labels, label_smoothing / num_classes -
                               1e4)  # With tolerance

  def test_mixup_changes_image(self):
    batch_size = 12
    num_classes = 1000
    label_smoothing = 0.1

    images = tf.random.normal((batch_size, 224, 224, 3), dtype=tf.float32)
    labels = tf.range(batch_size)
    augmenter = augment.MixupAndCutmix(
        mixup_alpha=1., cutmix_alpha=0., num_classes=num_classes)

    aug_images, aug_labels = augmenter.distort(images, labels)

    self.assertEqual(images.shape, aug_images.shape)
    self.assertEqual(images.dtype, aug_images.dtype)
    self.assertEqual([batch_size, num_classes], aug_labels.shape)
    self.assertAllLessEqual(aug_labels, 1. - label_smoothing +
                            2. / num_classes)  # With tolerance
    self.assertAllGreaterEqual(aug_labels, label_smoothing / num_classes -
                               1e4)  # With tolerance
    self.assertFalse(tf.math.reduce_all(images == aug_images))

  def test_cutmix_changes_image(self):
    batch_size = 12
    num_classes = 1000
    label_smoothing = 0.1

    images = tf.random.normal((batch_size, 224, 224, 3), dtype=tf.float32)
    labels = tf.range(batch_size)
    augmenter = augment.MixupAndCutmix(
        mixup_alpha=0., cutmix_alpha=1., num_classes=num_classes)

    aug_images, aug_labels = augmenter.distort(images, labels)

    self.assertEqual(images.shape, aug_images.shape)
    self.assertEqual(images.dtype, aug_images.dtype)
    self.assertEqual([batch_size, num_classes], aug_labels.shape)
    self.assertAllLessEqual(aug_labels, 1. - label_smoothing +
                            2. / num_classes)  # With tolerance
    self.assertAllGreaterEqual(aug_labels, label_smoothing / num_classes -
                               1e4)  # With tolerance
    self.assertFalse(tf.math.reduce_all(images == aug_images))


if __name__ == '__main__':
  tf.test.main()
