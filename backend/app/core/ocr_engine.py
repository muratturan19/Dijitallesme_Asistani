# -*- coding: utf-8 -*-
import logging
import re
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import numpy as np
import pytesseract
from PIL import Image

from app.config import settings

try:  # pragma: no cover - optional dependency
    import easyocr  # type: ignore
except ImportError:  # pragma: no cover - EasyOCR may be optional in some deployments
    easyocr = None  # type: ignore

logger = logging.getLogger(__name__)


class OCREngine:
    """OCR wrapper supporting both Tesseract and EasyOCR backends."""

    def __init__(
        self,
        tesseract_cmd: str,
        language: str = "tur+eng",
        *,
        engine: Optional[str] = None,
        use_easyocr: Optional[bool] = None,
        easyocr_languages: Optional[Sequence[str]] = None,
    ):
        """
        Initialize OCR engine

        Args:
            tesseract_cmd: Path to tesseract executable
            language: OCR language(s) - default Turkish + English
        """
        self.language = language or settings.TESSERACT_LANG
        self._tesseract_cmd = tesseract_cmd
        self._easyocr_reader: Optional[Any] = None
        self._easyocr_languages: Sequence[str] = []

        resolved_engine = self._resolve_engine_choice(use_easyocr, engine)
        self.engine = resolved_engine

        if self.engine == "easyocr":
            self._easyocr_languages = self._resolve_easyocr_languages(
                easyocr_languages
            )
            if not self._initialize_easyocr(self._easyocr_languages):
                logger.warning(
                    "EasyOCR başlatılamadı, Tesseract motoruna geri dönülüyor."
                )
                self.engine = "tesseract"

        if self.engine != "easyocr":
            self.engine = "tesseract"
            self._configure_tesseract()

    def _resolve_engine_choice(
        self, use_easyocr: Optional[bool], engine: Optional[str]
    ) -> str:
        if use_easyocr is not None:
            return "easyocr" if use_easyocr else "tesseract"

        if engine:
            normalized = engine.strip().lower()
            if normalized in {"easyocr", "tesseract"}:
                return normalized

        configured = str(getattr(settings, "OCR_ENGINE", "tesseract"))
        normalized = configured.strip().lower()
        return "easyocr" if normalized == "easyocr" else "tesseract"

    def _configure_tesseract(self) -> None:
        if self._tesseract_cmd and self._tesseract_cmd != "tesseract":
            pytesseract.pytesseract.tesseract_cmd = self._tesseract_cmd

        try:
            version = pytesseract.get_tesseract_version()
            logger.info("Tesseract versiyonu: %s", version)
        except Exception as exc:
            logger.error("Tesseract bulunamadı: %s", exc)
            logger.error(
                "Tesseract kurulumu gerekli: https://github.com/tesseract-ocr/tesseract"
            )

    def _resolve_easyocr_languages(
        self, languages: Optional[Sequence[str]] = None
    ) -> Sequence[str]:
        if languages:
            candidates = [str(lang).strip() for lang in languages if str(lang).strip()]
        else:
            raw = self.language or "tur+eng"
            segments = re.split(r"[+,]", raw)
            candidates = [segment.strip() for segment in segments if segment.strip()]

        mapping = {
            "tur": "tr",
            "trk": "tr",
            "tr": "tr",
            "eng": "en",
            "en": "en",
        }

        resolved: List[str] = []
        for code in candidates:
            normalized = code.lower()
            mapped = mapping.get(normalized, normalized)
            if mapped and mapped not in resolved:
                resolved.append(mapped)

        if not resolved:
            resolved = ["tr", "en"]

        return resolved

    def _initialize_easyocr(self, languages: Sequence[str]) -> bool:
        if easyocr is None:
            logger.warning("EasyOCR kütüphanesi yüklü değil.")
            return False

        try:
            self._easyocr_reader = easyocr.Reader(  # type: ignore[misc]
                list(languages),
                gpu=settings.EASYOCR_USE_GPU,
            )
            logger.info(
                "EasyOCR başlatıldı: diller=%s, gpu=%s",
                ",".join(languages),
                settings.EASYOCR_USE_GPU,
            )
            return True
        except Exception as exc:
            logger.error("EasyOCR başlatma hatası: %s", exc)
            self._easyocr_reader = None
            return False

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
            image = Image.open(image_path)
            processed_image = self._apply_roi(image, roi)

            if self.engine == "easyocr" and self._easyocr_reader is not None:
                result = self._extract_with_easyocr(processed_image)
            else:
                lang, config = self._build_tesseract_config(options)
                result = self._extract_with_tesseract(processed_image, lang, config)

            result['engine'] = self.engine

            logger.info(
                "OCR tamamlandı: engine=%s, kelime_sayısı=%s, ortalama_güven=%.2f",
                self.engine,
                result.get('word_count', 0),
                result.get('average_confidence', 0.0),
            )

            return result

        except Exception as e:
            logger.error("OCR hatası %s: %s", image_path, e)
            return {
                'text': '',
                'words_with_bbox': [],
                'confidence_scores': {},
                'average_confidence': 0.0,
                'word_count': 0,
                'error': str(e),
                'engine': self.engine,
            }

    def _extract_with_tesseract(
        self,
        image: Image.Image,
        lang: str,
        config: Optional[str],
    ) -> Dict[str, Any]:
        text = pytesseract.image_to_string(
            image,
            lang=lang,
            config=config,
        )

        data = pytesseract.image_to_data(
            image,
            lang=lang,
            config=config,
            output_type=pytesseract.Output.DICT,
        )

        words_with_bbox: List[Dict[str, Any]] = []
        confidence_scores: Dict[str, float] = {}
        total_conf = 0.0
        word_count = 0

        for i in range(len(data['text'])):
            word = data['text'][i].strip()
            if not word:
                continue

            try:
                conf = float(data['conf'][i])
            except (TypeError, ValueError):  # pragma: no cover - defensive
                continue

            if conf <= 0:
                continue

            normalized_conf = conf / 100.0
            word_data = {
                'word': word,
                'confidence': normalized_conf,
                'bbox': {
                    'x': data['left'][i],
                    'y': data['top'][i],
                    'w': data['width'][i],
                    'h': data['height'][i],
                },
                'line_num': data['line_num'][i],
                'block_num': data['block_num'][i],
            }

            words_with_bbox.append(word_data)
            confidence_scores[word] = normalized_conf
            total_conf += conf
            word_count += 1

        avg_confidence = (total_conf / word_count / 100.0) if word_count > 0 else 0.0

        return {
            'text': text.strip(),
            'words_with_bbox': words_with_bbox,
            'confidence_scores': confidence_scores,
            'average_confidence': avg_confidence,
            'word_count': word_count,
        }

    def _extract_with_easyocr(self, image: Image.Image) -> Dict[str, Any]:
        if self._easyocr_reader is None:
            raise RuntimeError("EasyOCR motoru başlatılmadı.")

        rgb_image = image.convert("RGB")
        np_image = np.array(rgb_image)

        detections = self._easyocr_reader.readtext(np_image, detail=1)

        segments: List[str] = []
        words_with_bbox: List[Dict[str, Any]] = []
        confidence_scores: Dict[str, float] = {}
        total_conf = 0.0
        token_count = 0

        for index, detection in enumerate(detections):
            if not isinstance(detection, (list, tuple)) or len(detection) < 3:
                continue

            bbox, text, confidence = detection[:3]
            text_value = (text or "").strip()
            if not text_value:
                continue

            normalized_conf = float(confidence or 0.0)
            normalized_conf = max(0.0, min(normalized_conf, 1.0))

            if isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
                xs = [point[0] for point in bbox if isinstance(point, (list, tuple))]
                ys = [point[1] for point in bbox if isinstance(point, (list, tuple))]
                if xs and ys:
                    x_min, x_max = min(xs), max(xs)
                    y_min, y_max = min(ys), max(ys)
                    bbox_dict = {
                        'x': int(x_min),
                        'y': int(y_min),
                        'w': int(x_max - x_min),
                        'h': int(y_max - y_min),
                    }
                else:
                    bbox_dict = {'x': 0, 'y': 0, 'w': 0, 'h': 0}
            else:
                bbox_dict = {'x': 0, 'y': 0, 'w': 0, 'h': 0}

            words_with_bbox.append(
                {
                    'word': text_value,
                    'confidence': normalized_conf,
                    'bbox': bbox_dict,
                    'line_num': index + 1,
                    'block_num': 1,
                }
            )

            tokens = [token for token in re.split(r"\s+", text_value) if token]
            if not tokens:
                tokens = [text_value]

            for token in tokens:
                confidence_scores[token] = normalized_conf
                total_conf += normalized_conf
            token_count += len(tokens)
            segments.append(text_value)

        average_confidence = (total_conf / token_count) if token_count else 0.0

        return {
            'text': "\n".join(segments).strip(),
            'words_with_bbox': words_with_bbox,
            'confidence_scores': confidence_scores,
            'average_confidence': average_confidence,
            'word_count': token_count,
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

            if self.engine == "easyocr" and self._easyocr_reader is not None:
                result = self._extract_with_easyocr(processed_image)
                return result.get('text', '')

            lang, config = self._build_tesseract_config(options)
            text = pytesseract.image_to_string(
                processed_image,
                lang=lang,
                config=config,
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
