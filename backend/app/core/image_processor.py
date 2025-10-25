# -*- coding: utf-8 -*-
import cv2
import numpy as np
from PIL import Image
import fitz  # PyMuPDF
from pathlib import Path
import logging
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass
import uuid
import re


@dataclass
class ProcessedDocument:
    """Container for processed document output."""

    text: Optional[str]
    image_path: Optional[str]
    source: str
    original_image_path: Optional[str] = None

logger = logging.getLogger(__name__)


class ImageProcessor:
    """Handles image preprocessing for OCR optimization"""

    def __init__(self, temp_dir: Path):
        self.temp_dir = temp_dir
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def process_file(
        self,
        file_path: str,
        profile: Optional[Dict[str, Any]] = None
    ) -> Optional[ProcessedDocument]:
        """
        Process uploaded file (PDF or image) and return either extracted text
        from the PDF text layer or the path to a preprocessed image ready for
        OCR.

        Args:
            file_path: Path to the uploaded file

        Returns:
            ProcessedDocument containing either text content or image path,
            or None if processing fails
        """
        try:
            file_path = Path(file_path)

            # Check if PDF or image
            if file_path.suffix.lower() == '.pdf':
                text_content = self._extract_pdf_text(file_path)

                if text_content:
                    logger.info(
                        "PDF metin katmanı bulundu, OCR atlanıyor: %s",
                        file_path
                    )
                    return ProcessedDocument(
                        text=text_content,
                        image_path=None,
                        source='text-layer'
                    )

                logger.info(
                    "PDF metin katmanı bulunamadı, OCR için dönüştürülüyor: %s",
                    file_path
                )
                image_path = self._pdf_to_image(file_path)
                original_image_path = image_path
            else:
                image_path = str(file_path)
                original_image_path = image_path

            # Preprocess the image with optional overrides
            preprocessed_path = self._preprocess_image(
                image_path,
                profile=profile
            )

            return ProcessedDocument(
                text=None,
                image_path=preprocessed_path,
                source='ocr',
                original_image_path=original_image_path
            )

        except Exception as e:
            logger.error(f"Dosya işleme hatası {file_path}: {str(e)}")
            return None

    def _extract_pdf_text(self, pdf_path: Path) -> str:
        """Return concatenated text-layer content for the PDF if available."""
        text_parts = []

        try:
            with fitz.open(str(pdf_path)) as doc:
                for page_num, page in enumerate(doc):
                    page_text = page.get_text("text") or ""

                    if page_text.strip():
                        logger.debug(
                            "PDF sayfası metin bulundu: %s (sayfa %d)",
                            pdf_path,
                            page_num + 1
                        )

                    text_parts.append(page_text)

        except Exception as e:
            logger.warning(f"PDF metin katmanı okunamadı {pdf_path}: {str(e)}")
            return ""

        text_content = "\n".join(part for part in text_parts if part).strip()

        if not text_content:
            logger.info("PDF metin katmanı boş: %s", pdf_path)

        return text_content

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

    def _preprocess_image(
        self,
        image_path: str,
        profile: Optional[Dict[str, Any]] = None
    ) -> str:
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

            processed_image = self._apply_preprocessing_steps(image, profile)

            # Save preprocessed image
            output_path = self.temp_dir / f"preprocessed_{Path(image_path).name}"
            cv2.imwrite(str(output_path), processed_image)

            logger.info(f"Resim işlendi: {output_path}")
            return str(output_path)

        except Exception as e:
            logger.error(f"Resim işleme hatası {image_path}: {str(e)}")
            # Return original image if preprocessing fails
            return str(image_path)

    def prepare_field_image(
        self,
        base_image_path: str,
        field_name: str,
        roi: Optional[Any] = None,
        preprocessing_profile: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """Crop and preprocess a specific field region for OCR."""

        try:
            image = cv2.imread(str(base_image_path))

            if image is None:
                raise ValueError(f"Resim okunamadı: {base_image_path}")

            crop_coords = None
            if roi is not None:
                crop_coords = self._parse_roi(roi, image)

            if crop_coords:
                x1, y1, x2, y2 = crop_coords
                image = image[y1:y2, x1:x2]

            processed = self._apply_preprocessing_steps(image, preprocessing_profile)

            safe_field = re.sub(r"[^A-Za-z0-9_-]+", "_", field_name).strip("_") or "field"
            output_name = (
                f"field_{safe_field}_{uuid.uuid4().hex[:8]}_{Path(base_image_path).stem}.png"
            )
            output_path = self.temp_dir / output_name
            cv2.imwrite(str(output_path), processed)

            return str(output_path)

        except Exception as exc:
            logger.error(
                "Alan görüntüsü hazırlanamadı %s (%s): %s",
                field_name,
                base_image_path,
                str(exc)
            )
            return None

    def _apply_preprocessing_steps(
        self,
        image: np.ndarray,
        profile: Optional[Dict[str, Any]] = None
    ) -> np.ndarray:
        """Apply preprocessing pipeline with configurable steps."""

        options = self._normalize_profile(profile)

        if image.ndim == 3:
            processed = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            processed = image.copy()

        if options['denoise']:
            h = int(options.get('denoise_strength', 10))
            processed = cv2.fastNlMeansDenoising(processed, None, h, 7, 21)

        if options['deskew']:
            processed = self._deskew(processed)

        if options['contrast']:
            clip_limit = float(options.get('clahe_clip_limit', 2.0))
            tile_grid = options.get('clahe_tile_grid_size', (8, 8))
            if isinstance(tile_grid, (list, tuple)) and len(tile_grid) == 2:
                tile_grid_size = (int(tile_grid[0]), int(tile_grid[1]))
            else:
                tile_grid_size = (8, 8)
            clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=tile_grid_size)
            processed = clahe.apply(processed)

        if options['threshold']:
            block_size = int(options.get('threshold_block_size', 11))
            if block_size % 2 == 0:
                block_size += 1
            constant = int(options.get('threshold_constant', 2))
            processed = cv2.adaptiveThreshold(
                processed,
                255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY,
                block_size,
                constant
            )

        return processed

    def _normalize_profile(
        self,
        profile: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Merge profile overrides with defaults."""

        defaults: Dict[str, Any] = {
            'denoise': True,
            'denoise_strength': 10,
            'deskew': True,
            'contrast': True,
            'clahe_clip_limit': 2.0,
            'clahe_tile_grid_size': (8, 8),
            'threshold': True,
            'threshold_block_size': 11,
            'threshold_constant': 2
        }

        if not profile:
            return defaults

        normalized = defaults.copy()
        for key, value in profile.items():
            if key not in normalized:
                if key == 'adaptive_threshold':
                    normalized['threshold'] = bool(value)
                else:
                    continue
            else:
                normalized[key] = value

        for boolean_key in ['denoise', 'deskew', 'contrast', 'threshold']:
            normalized[boolean_key] = bool(normalized.get(boolean_key))

        return normalized

    def _parse_roi(
        self,
        roi: Any,
        image: np.ndarray
    ) -> Optional[Tuple[int, int, int, int]]:
        """Normalize ROI definitions into pixel coordinates."""

        try:
            height, width = image.shape[:2]

            x = y = None
            w = h = None

            if isinstance(roi, (list, tuple)) and len(roi) >= 4:
                x, y, w, h = [int(float(val)) for val in roi[:4]]
            elif isinstance(roi, dict):
                x = int(float(roi.get('x', roi.get('left', 0))))
                y = int(float(roi.get('y', roi.get('top', 0))))

                if 'width' in roi or 'w' in roi:
                    w = int(float(roi.get('width', roi.get('w', 0))))
                elif 'x2' in roi:
                    w = int(float(roi['x2'])) - x

                if 'height' in roi or 'h' in roi:
                    h = int(float(roi.get('height', roi.get('h', 0))))
                elif 'y2' in roi:
                    h = int(float(roi['y2'])) - y
            else:
                return None

            if w is None or h is None:
                return None

            padding_x = padding_y = 0
            if isinstance(roi, dict) and roi.get('padding') is not None:
                padding = roi.get('padding')
                if isinstance(padding, (list, tuple)) and len(padding) >= 2:
                    padding_x = int(float(padding[0]))
                    padding_y = int(float(padding[1]))
                else:
                    padding_x = padding_y = int(float(padding))

            x1 = max(0, x - padding_x)
            y1 = max(0, y - padding_y)
            x2 = min(width, x + w + padding_x)
            y2 = min(height, y + h + padding_y)

            if x2 <= x1 or y2 <= y1:
                return None

            return x1, y1, x2, y2

        except Exception:
            return None

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
