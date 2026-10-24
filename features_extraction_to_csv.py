# Extract features from images and save into "features_all.csv"
# Optimized: only processes NEW students not already in CSV
import os
import dlib
import csv
import numpy as np
import logging
import cv2

path_images_from_camera = "data/data_faces_from_camera/"
detector        = dlib.get_frontal_face_detector()
predictor       = dlib.shape_predictor('data/data_dlib/shape_predictor_68_face_landmarks.dat')
face_reco_model = dlib.face_recognition_model_v1("data/data_dlib/dlib_face_recognition_resnet_model_v1.dat")


def return_128d_features(path_img):
    img_rd = cv2.imread(path_img)
    if img_rd is None:
        return 0
    faces = detector(img_rd, 1)
    if len(faces) != 0:
        shape = predictor(img_rd, faces[0])
        return face_reco_model.compute_face_descriptor(img_rd, shape)
    else:
        logging.warning("no face")
        return 0


def return_features_mean_personX(path_face_personX):
    features_list = []
    photos_list   = os.listdir(path_face_personX)
    for photo in photos_list:
        logging.info("%-40s %-20s", " / Reading image:", path_face_personX + "/" + photo)
        feat = return_128d_features(path_face_personX + "/" + photo)
        if feat != 0:
            features_list.append(feat)
    if features_list:
        return np.array(features_list, dtype=object).mean(axis=0)
    else:
        logging.warning(" Warning: No images in %s/", path_face_personX)
        return np.zeros(128, dtype=object, order='C')


def get_existing_names(csv_path):
    names = set()
    if os.path.isfile(csv_path):
        with open(csv_path, newline="") as f:
            for row in csv.reader(f):
                if row:
                    names.add(row[0].strip().lower())
    return names


def main():
    logging.basicConfig(level=logging.INFO)
    csv_path    = "data/features_all.csv"
    person_list = sorted(os.listdir(path_images_from_camera))

    existing_names = get_existing_names(csv_path)

    new_entries = []
    for person in person_list:
        person_path = path_images_from_camera + person
        if not os.path.isdir(person_path):
            continue

        parts = person.split('_', 2)
        person_name = parts[-1] if len(parts) == 3 else person

        if person_name.strip().lower() in existing_names:
            logging.info("Skipping (already processed): %s", person_name)
            continue

        logging.info("Processing NEW student: %s", person_name)
        features = return_features_mean_personX(person_path)
        row = np.insert(features, 0, person_name, axis=0)
        new_entries.append(row)
        logging.info("")

    if new_entries:
        with open(csv_path, "a", newline="") as csvfile:
            writer = csv.writer(csvfile)
            for entry in new_entries:
                writer.writerow(entry)
        logging.info("Added %d new student(s) to features_all.csv", len(new_entries))
    else:
        logging.info("No new students — CSV is already up to date!")

    logging.info("Done: data/features_all.csv")


if __name__ == '__main__':
    main()
