"""
Module with high level functionality for face detection
"""

import shapely.geometry
import numpy as np

import face.utilities
import face.geometry
import face.processing


class FaceCandidate:
    """
    A simple class representing an image crop that is to be examined for face presence.
    It contains three members:
    - crop_coordinates that specify coordinates of the crop in image it was taken from
    - cropped_image - cropped image
    - focus_coordinates - coordinates within original image for which face prediction score should of the crop
    should be used. These are generally within image_coordinates, but not necessary the same, since many partially
    overlapping crops might be examined
    """

    def __init__(self, crop_coordinates, cropped_image, focus_coordinates):
        """
        Constructor
        :param crop_coordinates: specify coordinates of the crop in image it was taken from
        :param cropped_image: cropped image
        :param focus_coordinates: coordinates within original image for which face prediction score should of the crop
        should be used. These are generally within image_coordinates, but not necessary the same, since many partially
        overlapping crops might be examined
        """

        self.crop_coordinates = crop_coordinates
        self.cropped_image = cropped_image
        self.focus_coordinates = focus_coordinates


class FaceDetection:
    """
    A very simple class representing a face detection. Contains face bounding box and detection score.
    """

    def __init__(self, bounding_box, score):
        """
        Constructor
        :param bounding_box: bounding box of the face
        :param score: confidence score of detection
        """

        self.bounding_box = bounding_box
        self.score = score

    def __eq__(self, other):
        """
        Equality comparison
        :param other: object to compare to
        :return: boolean value
        """

        if not isinstance(other, self.__class__):

            return False

        return self.bounding_box.equals(other.bounding_box) and self.score == other.score


def get_face_candidates(image, crop_size, stride):
    """
    Given an image, crop size and stride, get list of face candidates - crops of input image
    that will be examined for face presence. Each crop is of crop_size and crops are taken at stride distance from
     upper left corner of one crop to next crop (thus crops might be overlapping if stride is smaller than crop_size).
     Once all possible crops have been taken scanning image in one row, scanning proceeds from first column of
     row stride away from current row.
    :param image: image from which crops are to be taken
    :param crop_size: size of each crop
    :param stride: stride at which crops should be taken. Must be not larger than crop size.
    :return: list of FaceCandidate objects
    """

    if crop_size < stride:

        raise ValueError("Crop size ({}) must be not smaller than stride size ({})".format(crop_size, stride))

    face_candidates = []

    offset = (crop_size - stride) // 2

    y = 0

    while y + crop_size <= image.shape[0]:

        x = 0

        while x + crop_size <= image.shape[1]:

            crop_coordinates = shapely.geometry.box(x, y, x + crop_size, y + crop_size)
            cropped_image = image[y:y + crop_size, x:x + crop_size]

            focus_coordinates = shapely.geometry.box(x + offset, y + offset, x + crop_size - offset, y + crop_size - offset)

            candidate = FaceCandidate(crop_coordinates, cropped_image, focus_coordinates)
            face_candidates.append(candidate)

            x += stride

        y += stride

    return face_candidates


class HeatmapComputer:
    """
    Class for computing face presence heatmap given an image, prediction model and scanning parameters.
    """

    def __init__(self, image, model, configuration):
        """
        Constructor
        :param image: image to compute heatmap for
        :param model: face prediction model
        :param configuration: FaceSearchConfiguration instance
        """

        self.image = image
        self.model = model
        self.configuration = configuration

    def get_heatmap(self):
        """
        Returns heatmap
        :return: 2D numpy array of same size as image used to construct class HeatmapComputer instance
        """

        heatmap = np.zeros(shape=self.image.shape[:2], dtype=np.float32)

        face_candidates = get_face_candidates(self.image, self.configuration.crop_size, self.configuration.stride)
        scores = self._get_candidate_scores(face_candidates)

        for face_candidate, score in zip(face_candidates, scores):

            x_start, y_start, x_end, y_end = [int(value) for value in face_candidate.focus_coordinates.bounds]
            heatmap[y_start:y_end, x_start:x_end] = score

        return heatmap

    def _get_candidate_scores(self, face_candidates):

        face_crops = [candidate.cropped_image for candidate in face_candidates]
        face_crops_batches = face.utilities.get_batches(face_crops, self.configuration.batch_size)

        scores = []

        for batch in face_crops_batches:

            predictions_batch = self.model.predict(np.array(batch))
            scores.extend(predictions_batch)

        return scores


class MultiScaleHeatmapComputer:
    """
    Class for computing face presence heatmap given an image, prediction model and scanning parameters.
    Scanning is performed at multiple scales.
    """

    def __init__(self, image, model, configuration):
        """
        Constructor
        :param image: image to compute heatmap for
        :param model: face prediction model
        :param configuration: MultiScaleFaceSearchConfiguration instance
        """

        self.image = image
        self.model = model
        self.configuration = configuration

    def get_heatmap(self):
        """
        Returns heatmap
        :return: 2D numpy array of same size as image used to construct class HeatmapComputer instance
        """

        heatmap = np.zeros(shape=self.image.shape[:2], dtype=np.float32)

        # Get smallest size at which we want to search for a face in the image
        # smallest_face_size = face.processing.get_smallest_expected_face_size(image.shape)

        return heatmap






def get_unique_face_detections(face_detections):
    """
    Given a list of FaceDetection objects, return only unique face detections, filtering out similar detections
    so that for each group of similar detections only a single one remains in output list
    :param face_detections: list of FaceDetection objects
    :return: list of FaceDetection objects
    """

    unique_detections = []

    for detection in face_detections:

        unique_id = 0
        similar_detection_found = False

        while unique_id < len(unique_detections) and similar_detection_found is False:

            unique_detection = unique_detections[unique_id]

            if face.geometry.get_intersection_over_union(detection.bounding_box, unique_detection.bounding_box) > 0.3:

                unique_detections[unique_id] = unique_detection \
                    if unique_detection.score > detection.score else detection

                similar_detection_found = True

            unique_id += 1

        if similar_detection_found is False:

            unique_detections.append(detection)

    return unique_detections


class FaceDetector:
    """
    Class for detecting faces in images. Given an image, prediction model and scanning parameters,
    returns a list of FaceDetection instances.
    """

    def __init__(self, image, model, configuration):
        """
        Constructor
        :param image: image to search
        :param model: face detection model
        :param configuration: FaceSearchConfiguration instance
        """

        self.image = image
        self.model = model
        self.configuration = configuration

    def get_faces_bounding_boxes(self):
        """
        Get bouding boxes of faces found in image FaceDetector instance was constructed with
        :return: a list of bounding boxes
        """

        face_candidates = get_face_candidates(self.image, self.configuration.crop_size, self.configuration.stride)
        scores = self._get_candidate_scores(face_candidates)

        face_detections = []

        for candidate, score in zip(face_candidates, scores):

            if score > 0.5:

                detection = FaceDetection(candidate.crop_coordinates, score)
                face_detections.append(detection)

        unique_detections = get_unique_face_detections(face_detections)

        return [detection.bounding_box for detection in unique_detections]

    def _get_candidate_scores(self, face_candidates):

        face_crops = [candidate.cropped_image for candidate in face_candidates]
        face_crops_batches = face.utilities.get_batches(face_crops, self.configuration.batch_size)

        scores = []

        for batch in face_crops_batches:

            predictions_batch = self.model.predict(np.array(batch))
            scores.extend(predictions_batch)

        return scores
