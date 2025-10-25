# -*- coding: utf-8 -*-
import cv2
import numpy as np
from PIL import Image
import fitz  # PyMuPDF
from pathlib import Path
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class ImageProcessor:
    """Handles image preprocessing for OCR optimization"""

    def __init__(self, temp_dir: Path):
        self.temp_dir = temp_dir
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def process_file(self, file_path: str) -> Optional[str]:
        """
        Process uploaded file (PDF or image) and return preprocessed image path

        Args:
            file_path: Path to the uploaded file

        Returns:
            Path to preprocessed image or None if processing fails
        """
        try:
            file_path = Path(file_path)

            # Check if PDF or image
            if file_path.suffix.lower() == '.pdf':
                image_path = self._pdf_to_image(file_path)
            else:
                image_path = str(file_path)

            # Preprocess the image
            preprocessed_path = self._preprocess_image(image_path)

            return preprocessed_path

        except Exception as e:
            logger.error(f"Dosya işleme hatası {file_path}: {str(e)}")
            return None

    def _pdf_to_image(self, pdf_path: Path) -> str:
        """
        Convert PDF first page to image

        Args:
            pdf_path: Path to PDF file

        Returns:
            Path to converted image
        """
        try:
            # Open PDF
            doc = fitz.open(str(pdf_path))

            # Get first page
            page = doc[0]

            # Render page to image (high DPI for better OCR)
            mat = fitz.Matrix(2.0, 2.0)  # 2x zoom for 144 DPI
            pix = page.get_pixmap(matrix=mat)

            # Save as PNG
            output_path = self.temp_dir / f"{pdf_path.stem}_page1.png"
            pix.save(str(output_path))

            doc.close()

            logger.info(f"PDF dönüştürüldü: {output_path}")
            return str(output_path)

        except Exception as e:
            logger.error(f"PDF dönüştürme hatası {pdf_path}: {str(e)}")
            raise

    def _preprocess_image(self, image_path: str) -> str:
        """
        Preprocess image for better OCR results

        Steps:
        1. Convert to grayscale
        2. Denoise
        3. Deskew
        4. Enhance contrast
        5. Binarization (adaptive threshold)

        Args:
            image_path: Path to image file

        Returns:
            Path to preprocessed image
        """
        try:
            # Read image
            image = cv2.imread(str(image_path))

            if image is None:
                raise ValueError(f"Resim okunamadı: {image_path}")

            # 1. Convert to grayscale
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

            # 2. Denoise
            denoised = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)

            # 3. Deskew
            deskewed = self._deskew(denoised)

            # 4. Enhance contrast (CLAHE - Contrast Limited Adaptive Histogram Equalization)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            enhanced = clahe.apply(deskewed)

            # 5. Adaptive thresholding for binarization
            binary = cv2.adaptiveThreshold(
                enhanced,
                255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY,
                11,
                2
            )

            # Save preprocessed image
            output_path = self.temp_dir / f"preprocessed_{Path(image_path).name}"
            cv2.imwrite(str(output_path), binary)

            logger.info(f"Resim işlendi: {output_path}")
            return str(output_path)

        except Exception as e:
            logger.error(f"Resim işleme hatası {image_path}: {str(e)}")
            # Return original image if preprocessing fails
            return str(image_path)

    def _deskew(self, image: np.ndarray) -> np.ndarray:
        """
        Correct image skew/rotation

        Args:
            image: Grayscale image array

        Returns:
            Deskewed image array
        """
        try:
            # Detect edges
            edges = cv2.Canny(image, 50, 150, apertureSize=3)

            # Detect lines using Hough transform
            lines = cv2.HoughLines(edges, 1, np.pi / 180, 200)

            if lines is None or len(lines) == 0:
                return image

            # Calculate average angle
            angles = []
            for rho, theta in lines[:, 0]:
                angle = np.rad2deg(theta) - 90
                if abs(angle) < 45:  # Only consider reasonable angles
                    angles.append(angle)

            if not angles:
                return image

            median_angle = np.median(angles)

            # Only rotate if angle is significant (> 0.5 degrees)
            if abs(median_angle) < 0.5:
                return image

            # Rotate image
            (h, w) = image.shape[:2]
            center = (w // 2, h // 2)
            M = cv2.getRotationMatrix2D(center, median_angle, 1.0)
            rotated = cv2.warpAffine(
                image,
                M,
                (w, h),
                flags=cv2.INTER_CUBIC,
                borderMode=cv2.BORDER_REPLICATE
            )

            logger.info(f"Resim döndürüldü: {median_angle:.2f} derece")
            return rotated

        except Exception as e:
            logger.warning(f"Deskew hatası: {str(e)}")
            return image

    def get_image_info(self, image_path: str) -> dict:
        """
        Get image metadata

        Args:
            image_path: Path to image file

        Returns:
            Dictionary with image info
        """
        try:
            with Image.open(image_path) as img:
                return {
                    "width": img.width,
                    "height": img.height,
                    "format": img.format,
                    "mode": img.mode,
                    "dpi": img.info.get("dpi", (72, 72))
                }
        except Exception as e:
            logger.error(f"Resim bilgisi alınamadı {image_path}: {str(e)}")
            return {}
