# -*- coding: utf-8 -*-
import pytesseract
from PIL import Image
import logging
from typing import Dict, List, Optional, Any, Tuple, Union
import sys

logger = logging.getLogger(__name__)


class OCREngine:
    """Tesseract OCR wrapper for text extraction"""

    def __init__(self, tesseract_cmd: str, language: str = "tur+eng"):
        """
        Initialize OCR engine

        Args:
            tesseract_cmd: Path to tesseract executable
            language: OCR language(s) - default Turkish + English
        """
        self.language = language

        # Set Tesseract command path
        if tesseract_cmd and tesseract_cmd != "tesseract":
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

        # Verify Tesseract is installed
        try:
            version = pytesseract.get_tesseract_version()
            logger.info(f"Tesseract versiyonu: {version}")
        except Exception as e:
            logger.error(f"Tesseract bulunamadı: {str(e)}")
            logger.error("Tesseract kurulumu gerekli: https://github.com/tesseract-ocr/tesseract")

    def extract_text(
        self,
        image_path: str,
        options: Optional[Dict[str, Any]] = None,
        roi: Optional[Union[Dict[str, Any], List[int], Tuple[int, int, int, int]]] = None
    ) -> Dict[str, Any]:
        """
        Extract text from image with detailed information

        Args:
            image_path: Path to image file

        Returns:
            Dictionary containing:
                - text: Full extracted text
                - words_with_bbox: List of words with bounding boxes
                - confidence_scores: Confidence score for each word
                - average_confidence: Overall confidence
        """
        try:
            # Open image
            image = Image.open(image_path)
            processed_image = self._apply_roi(image, roi)

            lang, config = self._build_tesseract_config(options)

            # Extract text
            text = pytesseract.image_to_string(
                processed_image,
                lang=lang,
                config=config
            )

            # Extract detailed data (word-level)
            data = pytesseract.image_to_data(
                processed_image,
                lang=lang,
                config=config,
                output_type=pytesseract.Output.DICT
            )

            # Process word-level data
            words_with_bbox = []
            confidence_scores = {}
            total_conf = 0
            word_count = 0

            for i in range(len(data['text'])):
                word = data['text'][i].strip()

                if word:  # Only process non-empty words
                    conf = int(data['conf'][i])

                    if conf > 0:  # Only include words with valid confidence
                        word_data = {
                            'word': word,
                            'confidence': conf / 100.0,  # Normalize to 0-1
                            'bbox': {
                                'x': data['left'][i],
                                'y': data['top'][i],
                                'w': data['width'][i],
                                'h': data['height'][i]
                            },
                            'line_num': data['line_num'][i],
                            'block_num': data['block_num'][i]
                        }

                        words_with_bbox.append(word_data)
                        confidence_scores[word] = conf / 100.0

                        total_conf += conf
                        word_count += 1

            # Calculate average confidence
            avg_confidence = (total_conf / word_count / 100.0) if word_count > 0 else 0.0

            result = {
                'text': text.strip(),
                'words_with_bbox': words_with_bbox,
                'confidence_scores': confidence_scores,
                'average_confidence': avg_confidence,
                'word_count': word_count
            }

            logger.info(
                f"OCR tamamlandı: {word_count} kelime, "
                f"ortalama güven: {avg_confidence:.2f}"
            )

            return result

        except Exception as e:
            logger.error(f"OCR hatası {image_path}: {str(e)}")
            return {
                'text': '',
                'words_with_bbox': [],
                'confidence_scores': {},
                'average_confidence': 0.0,
                'word_count': 0,
                'error': str(e)
            }

    def extract_text_simple(
        self,
        image_path: str,
        options: Optional[Dict[str, Any]] = None,
        roi: Optional[Union[Dict[str, Any], List[int], Tuple[int, int, int, int]]] = None
    ) -> str:
        """
        Simple text extraction (just the text)

        Args:
            image_path: Path to image file

        Returns:
            Extracted text string
        """
        try:
            image = Image.open(image_path)
            processed_image = self._apply_roi(image, roi)

            lang, config = self._build_tesseract_config(options)

            text = pytesseract.image_to_string(
                processed_image,
                lang=lang,
                config=config
            )
            return text.strip()
        except Exception as e:
            logger.error(f"OCR hatası {image_path}: {str(e)}")
            return ""

    def extract_regions(
        self,
        image_path: str,
        regions: List[Dict[str, Any]],
        base_options: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Dict[str, Any]]:
        """Run OCR on multiple regions with optional per-region overrides."""

        results: Dict[str, Dict[str, Any]] = {}

        if not regions:
            return results

        for index, region in enumerate(regions):
            label = str(region.get('id') or region.get('field') or index)
            roi = region.get('roi', region.get('box', region.get('region')))

            region_options: Dict[str, Any] = {}
            if base_options:
                region_options.update(base_options)
            if isinstance(region.get('options'), dict):
                region_options.update(region['options'])
            if isinstance(region.get('ocr_options'), dict):
                region_options.update(region['ocr_options'])

            results[label] = self.extract_text(
                image_path,
                options=region_options if region_options else None,
                roi=roi
            )

        return results

    def extract_structured_data(self, image_path: str) -> Dict[str, List[str]]:
        """
        Extract text organized by lines and blocks

        Args:
            image_path: Path to image file

        Returns:
            Dictionary with text organized by structure
        """
        try:
            image = Image.open(image_path)

            # Get detailed OCR data
            data = pytesseract.image_to_data(
                image,
                lang=self.language,
                output_type=pytesseract.Output.DICT
            )

            # Organize by blocks and lines
            blocks = {}
            current_block = None
            current_line = None

            for i in range(len(data['text'])):
                word = data['text'][i].strip()

                if not word:
                    continue

                block_num = data['block_num'][i]
                line_num = data['line_num'][i]

                # Initialize block if needed
                if block_num not in blocks:
                    blocks[block_num] = {}

                # Initialize line if needed
                if line_num not in blocks[block_num]:
                    blocks[block_num][line_num] = []

                # Add word to line
                blocks[block_num][line_num].append(word)

            # Convert to structured format
            structured = {
                'blocks': [],
                'lines': [],
                'all_text': []
            }

            for block_num in sorted(blocks.keys()):
                block_lines = []
                for line_num in sorted(blocks[block_num].keys()):
                    line_text = ' '.join(blocks[block_num][line_num])
                    block_lines.append(line_text)
                    structured['lines'].append(line_text)

                block_text = '\n'.join(block_lines)
                structured['blocks'].append(block_text)
                structured['all_text'].append(block_text)

            return structured

        except Exception as e:
            logger.error(f"Yapılandırılmış OCR hatası {image_path}: {str(e)}")
            return {'blocks': [], 'lines': [], 'all_text': []}

    def get_available_languages(self) -> List[str]:
        """
        Get list of available Tesseract languages

        Returns:
            List of language codes
        """
        try:
            langs = pytesseract.get_languages()
            return langs
        except Exception as e:
            logger.error(f"Dil listesi alınamadı: {str(e)}")
            return []

    def _build_tesseract_config(
        self,
        options: Optional[Dict[str, Any]] = None
    ) -> Tuple[str, Optional[str]]:
        """Construct language and config string for Tesseract."""

        lang = self.language
        config_parts: List[str] = []

        if options:
            if options.get('language'):
                lang = options['language']

            custom_config = options.get('config')
            if isinstance(custom_config, (list, tuple)):
                config_parts.extend(str(item) for item in custom_config if item)
            elif isinstance(custom_config, str):
                config_parts.append(custom_config)

            psm_value = options.get('psm')
            psm_in_config = any('--psm' in str(part) for part in config_parts)
            if psm_value is not None:
                if not psm_in_config:
                    config_parts.append(f'--psm {int(psm_value)}')
            elif not psm_in_config:
                config_parts.append('--psm 3')

            oem_value = options.get('oem')
            if oem_value is not None:
                config_parts.append(f'--oem {int(oem_value)}')

            whitelist = options.get('whitelist') or options.get('char_whitelist')
            if whitelist:
                config_parts.append(f'-c tessedit_char_whitelist={whitelist}')

            blacklist = options.get('blacklist')
            if blacklist:
                config_parts.append(f'-c tessedit_char_blacklist={blacklist}')

            dpi = options.get('dpi')
            if dpi is not None:
                config_parts.append(f'--dpi {int(dpi)}')

            variables = options.get('variables')
            if isinstance(variables, dict):
                for key, value in variables.items():
                    config_parts.append(f'-c {key}={value}')
        else:
            config_parts.append('--psm 3')

        config = ' '.join(str(part) for part in config_parts if str(part).strip())
        return lang, config if config else None

    def _apply_roi(
        self,
        image: Image.Image,
        roi: Optional[Union[Dict[str, Any], List[int], Tuple[int, int, int, int]]]
    ) -> Image.Image:
        """Crop PIL image according to ROI definition if provided."""

        if roi is None:
            return image

        box = self._normalize_roi_box(roi, image.size)
        if not box:
            return image

        try:
            return image.crop(box)
        except Exception:
            return image

    def _normalize_roi_box(
        self,
        roi: Union[Dict[str, Any], List[int], Tuple[int, ...]],
        image_size: Tuple[int, int]
    ) -> Optional[Tuple[int, int, int, int]]:
        """Normalize ROI definitions into a PIL crop box."""

        try:
            width, height = image_size

            if isinstance(roi, (list, tuple)):
                if len(roi) == 4 and all(isinstance(val, (int, float)) for val in roi):
                    x, y, w, h = roi
                elif roi and isinstance(roi[0], (list, tuple, dict)):
                    # Nested ROI definitions - use the first entry
                    return self._normalize_roi_box(roi[0], image_size)
                else:
                    return None
            elif isinstance(roi, dict):
                x = float(roi.get('x', roi.get('left', 0)))
                y = float(roi.get('y', roi.get('top', 0)))
                if 'width' in roi or 'w' in roi:
                    w = float(roi.get('width', roi.get('w', 0)))
                elif 'x2' in roi:
                    w = float(roi['x2']) - x
                else:
                    w = 0

                if 'height' in roi or 'h' in roi:
                    h = float(roi.get('height', roi.get('h', 0)))
                elif 'y2' in roi:
                    h = float(roi['y2']) - y
                else:
                    h = 0

                padding_x = padding_y = 0
                if roi.get('padding') is not None:
                    padding = roi['padding']
                    if isinstance(padding, (list, tuple)) and len(padding) >= 2:
                        padding_x = float(padding[0])
                        padding_y = float(padding[1])
                    else:
                        padding_x = padding_y = float(padding)

                x -= padding_x
                y -= padding_y
                w += padding_x * 2
                h += padding_y * 2
            else:
                return None

            x1 = max(0, int(x))
            y1 = max(0, int(y))
            x2 = min(width, int(x + w))
            y2 = min(height, int(y + h))

            if x2 <= x1 or y2 <= y1:
                return None

            return x1, y1, x2, y2

        except Exception:
            return None
