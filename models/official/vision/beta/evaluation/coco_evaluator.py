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

"""The COCO-style evaluator.

The following snippet demonstrates the use of interfaces:

  evaluator = COCOEvaluator(...)
  for _ in range(num_evals):
    for _ in range(num_batches_per_eval):
      predictions, groundtruth = predictor.predict(...)  # pop a batch.
      evaluator.update_state(groundtruths, predictions)
    evaluator.result()  # finish one full eval and reset states.

See also: https://github.com/cocodataset/cocoapi/
"""

import atexit
import tempfile
# Import libraries
from absl import logging
import numpy as np
from pycocotools import cocoeval
import six
import tensorflow as tf

from models.official.vision.beta.evaluation import coco_utils


class COCOEvaluator(object):
  """COCO evaluation metric class."""

  def __init__(self,
               annotation_file,
               include_mask,
               need_rescale_bboxes=True,
               per_category_metrics=False):
    """Constructs COCO evaluation class.

    The class provides the interface to COCO metrics_fn. The
    _update_op() takes detections from each image and push them to
    self.detections. The _evaluate() loads a JSON file in COCO annotation format
    as the groundtruths and runs COCO evaluation.

    Args:
      annotation_file: a JSON file that stores annotations of the eval dataset.
        If `annotation_file` is None, groundtruth annotations will be loaded
        from the dataloader.
      include_mask: a boolean to indicate whether or not to include the mask
        eval.
      need_rescale_bboxes: If true bboxes in `predictions` will be rescaled back
        to absolute values (`image_info` is needed in this case).
      per_category_metrics: Whether to return per category metrics.
    """
    if annotation_file:
      if annotation_file.startswith('gs://'):
        _, local_val_json = tempfile.mkstemp(suffix='.json')
        tf.io.gfile.remove(local_val_json)

        tf.io.gfile.copy(annotation_file, local_val_json)
        atexit.register(tf.io.gfile.remove, local_val_json)
      else:
        local_val_json = annotation_file
      self._coco_gt = coco_utils.COCOWrapper(
          eval_type=('mask' if include_mask else 'box'),
          annotation_file=local_val_json)
    self._annotation_file = annotation_file
    self._include_mask = include_mask
    self._per_category_metrics = per_category_metrics
    self._metric_names = [
        'AP', 'AP50', 'AP75', 'APs', 'APm', 'APl', 'ARmax1', 'ARmax10',
        'ARmax100', 'ARs', 'ARm', 'ARl'
    ]
    self._required_prediction_fields = [
        'source_id', 'num_detections', 'detection_classes', 'detection_scores',
        'detection_boxes'
    ]
    self._need_rescale_bboxes = need_rescale_bboxes
    if self._need_rescale_bboxes:
      self._required_prediction_fields.append('image_info')
    self._required_groundtruth_fields = [
        'source_id', 'height', 'width', 'classes', 'boxes'
    ]
    if self._include_mask:
      mask_metric_names = ['mask_' + x for x in self._metric_names]
      self._metric_names.extend(mask_metric_names)
      self._required_prediction_fields.extend(['detection_masks'])
      self._required_groundtruth_fields.extend(['masks'])

    self.reset_states()

  @property
  def name(self):
    return 'coco_metric'

  def reset_states(self):
    """Resets internal states for a fresh run."""
    self._predictions = {}
    if not self._annotation_file:
      self._groundtruths = {}

  def result(self):
    """Evaluates detection results, and reset_states."""
    metric_dict = self.evaluate()
    # Cleans up the internal variables in order for a fresh eval next time.
    self.reset_states()
    return metric_dict

  def evaluate(self):
    """Evaluates with detections from all images with COCO API.

    Returns:
      coco_metric: float numpy array with shape [24] representing the
        coco-style evaluation metrics (box and mask).
    """
    if not self._annotation_file:
      logging.info('There is no annotation_file in COCOEvaluator.')
      gt_dataset = coco_utils.convert_groundtruths_to_coco_dataset(
          self._groundtruths)
      coco_gt = coco_utils.COCOWrapper(
          eval_type=('mask' if self._include_mask else 'box'),
          gt_dataset=gt_dataset)
    else:
      logging.info('Using annotation file: %s', self._annotation_file)
      coco_gt = self._coco_gt
    coco_predictions = coco_utils.convert_predictions_to_coco_annotations(
        self._predictions)
    coco_dt = coco_gt.loadRes(predictions=coco_predictions)
    image_ids = [ann['image_id'] for ann in coco_predictions]

    coco_eval = cocoeval.COCOeval(coco_gt, coco_dt, iouType='bbox')
    coco_eval.params.imgIds = image_ids
    coco_eval.evaluate()
    coco_eval.accumulate()
    coco_eval.summarize()
    coco_metrics = coco_eval.stats

    if self._include_mask:
      mcoco_eval = cocoeval.COCOeval(coco_gt, coco_dt, iouType='segm')
      mcoco_eval.params.imgIds = image_ids
      mcoco_eval.evaluate()
      mcoco_eval.accumulate()
      mcoco_eval.summarize()
      mask_coco_metrics = mcoco_eval.stats

    if self._include_mask:
      metrics = np.hstack((coco_metrics, mask_coco_metrics))
    else:
      metrics = coco_metrics

    metrics_dict = {}
    for i, name in enumerate(self._metric_names):
      metrics_dict[name] = metrics[i].astype(np.float32)

    # Adds metrics per category.
    if self._per_category_metrics:
      metrics_dict.update(self._retrieve_per_category_metrics(coco_eval))

      if self._include_mask:
        metrics_dict.update(self._retrieve_per_category_metrics(
            mcoco_eval, prefix='mask'))

    return metrics_dict

  def _retrieve_per_category_metrics(self, coco_eval, prefix=''):
    """Retrieves and per-category metrics and retuns them in a dict.

    Args:
      coco_eval: a cocoeval.COCOeval object containing evaluation data.
      prefix: str, A string used to prefix metric names.

    Returns:
      metrics_dict: A dictionary with per category metrics.
    """

    metrics_dict = {}
    if prefix:
      prefix = prefix + ' '

    if hasattr(coco_eval, 'category_stats'):
      for category_index, category_id in enumerate(coco_eval.params.catIds):
        if self._annotation_file:
          coco_category = self._coco_gt.cats[category_id]
          # if 'name' is available use it, otherwise use `id`
          category_display_name = coco_category.get('name', category_id)
        else:
          category_display_name = category_id

        metrics_dict[prefix + 'Precision mAP ByCategory/{}'.format(
            category_display_name
        )] = coco_eval.category_stats[0][category_index].astype(np.float32)
        metrics_dict[prefix + 'Precision mAP ByCategory@50IoU/{}'.format(
            category_display_name
        )] = coco_eval.category_stats[1][category_index].astype(np.float32)
        metrics_dict[prefix + 'Precision mAP ByCategory@75IoU/{}'.format(
            category_display_name
        )] = coco_eval.category_stats[2][category_index].astype(np.float32)
        metrics_dict[prefix + 'Precision mAP ByCategory (small) /{}'.format(
            category_display_name
        )] = coco_eval.category_stats[3][category_index].astype(np.float32)
        metrics_dict[prefix + 'Precision mAP ByCategory (medium) /{}'.format(
            category_display_name
        )] = coco_eval.category_stats[4][category_index].astype(np.float32)
        metrics_dict[prefix + 'Precision mAP ByCategory (large) /{}'.format(
            category_display_name
        )] = coco_eval.category_stats[5][category_index].astype(np.float32)
        metrics_dict[prefix + 'Recall AR@1 ByCategory/{}'.format(
            category_display_name
        )] = coco_eval.category_stats[6][category_index].astype(np.float32)
        metrics_dict[prefix + 'Recall AR@10 ByCategory/{}'.format(
            category_display_name
        )] = coco_eval.category_stats[7][category_index].astype(np.float32)
        metrics_dict[prefix + 'Recall AR@100 ByCategory/{}'.format(
            category_display_name
        )] = coco_eval.category_stats[8][category_index].astype(np.float32)
        metrics_dict[prefix + 'Recall AR (small) ByCategory/{}'.format(
            category_display_name
        )] = coco_eval.category_stats[9][category_index].astype(np.float32)
        metrics_dict[prefix + 'Recall AR (medium) ByCategory/{}'.format(
            category_display_name
        )] = coco_eval.category_stats[10][category_index].astype(np.float32)
        metrics_dict[prefix + 'Recall AR (large) ByCategory/{}'.format(
            category_display_name
        )] = coco_eval.category_stats[11][category_index].astype(np.float32)

    return metrics_dict

  def _process_predictions(self, predictions):
    image_scale = np.tile(predictions['image_info'][:, 2:3, :], (1, 1, 2))
    predictions['detection_boxes'] = (
        predictions['detection_boxes'].astype(np.float32))
    predictions['detection_boxes'] /= image_scale
    if 'detection_outer_boxes' in predictions:
      predictions['detection_outer_boxes'] = (
          predictions['detection_outer_boxes'].astype(np.float32))
      predictions['detection_outer_boxes'] /= image_scale

  def _convert_to_numpy(self, groundtruths, predictions):
    """Converts tesnors to numpy arrays."""
    if groundtruths:
      labels = tf.nest.map_structure(lambda x: x.numpy(), groundtruths)
      numpy_groundtruths = {}
      for key, val in labels.items():
        if isinstance(val, tuple):
          val = np.concatenate(val)
        numpy_groundtruths[key] = val
    else:
      numpy_groundtruths = groundtruths

    if predictions:
      outputs = tf.nest.map_structure(lambda x: x.numpy(), predictions)
      numpy_predictions = {}
      for key, val in outputs.items():
        if isinstance(val, tuple):
          val = np.concatenate(val)
        numpy_predictions[key] = val
    else:
      numpy_predictions = predictions

    return numpy_groundtruths, numpy_predictions

  def update_state(self, groundtruths, predictions):
    """Update and aggregate detection results and groundtruth data.

    Args:
      groundtruths: a dictionary of Tensors including the fields below.
        See also different parsers under `../dataloader` for more details.
        Required fields:
          - source_id: a numpy array of int or string of shape [batch_size].
          - height: a numpy array of int of shape [batch_size].
          - width: a numpy array of int of shape [batch_size].
          - num_detections: a numpy array of int of shape [batch_size].
          - boxes: a numpy array of float of shape [batch_size, K, 4].
          - classes: a numpy array of int of shape [batch_size, K].
        Optional fields:
          - is_crowds: a numpy array of int of shape [batch_size, K]. If the
              field is absent, it is assumed that this instance is not crowd.
          - areas: a numy array of float of shape [batch_size, K]. If the
              field is absent, the area is calculated using either boxes or
              masks depending on which one is available.
          - masks: a numpy array of float of shape
              [batch_size, K, mask_height, mask_width],
      predictions: a dictionary of tensors including the fields below.
        See different parsers under `../dataloader` for more details.
        Required fields:
          - source_id: a numpy array of int or string of shape [batch_size].
          - image_info [if `need_rescale_bboxes` is True]: a numpy array of
            float of shape [batch_size, 4, 2].
          - num_detections: a numpy array of
            int of shape [batch_size].
          - detection_boxes: a numpy array of float of shape [batch_size, K, 4].
          - detection_classes: a numpy array of int of shape [batch_size, K].
          - detection_scores: a numpy array of float of shape [batch_size, K].
        Optional fields:
          - detection_masks: a numpy array of float of shape
              [batch_size, K, mask_height, mask_width].
    Raises:
      ValueError: if the required prediction or groundtruth fields are not
        present in the incoming `predictions` or `groundtruths`.
    """
    groundtruths, predictions = self._convert_to_numpy(groundtruths,
                                                       predictions)
    for k in self._required_prediction_fields:
      if k not in predictions:
        raise ValueError(
            'Missing the required key `{}` in predictions!'.format(k))
    if self._need_rescale_bboxes:
      self._process_predictions(predictions)
    for k, v in six.iteritems(predictions):
      if k not in self._predictions:
        self._predictions[k] = [v]
      else:
        self._predictions[k].append(v)

    if not self._annotation_file:
      assert groundtruths
      for k in self._required_groundtruth_fields:
        if k not in groundtruths:
          raise ValueError(
              'Missing the required key `{}` in groundtruths!'.format(k))
      for k, v in six.iteritems(groundtruths):
        if k not in self._groundtruths:
          self._groundtruths[k] = [v]
        else:
          self._groundtruths[k].append(v)
