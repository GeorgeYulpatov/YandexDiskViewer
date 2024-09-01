import logging
from typing import Any
from urllib.parse import quote
from django.core.cache import cache
from django.shortcuts import render
from django.http import HttpResponse, JsonResponse
from .forms import PublicLinkForm
import requests
from io import BytesIO
import zipfile

# Настройка логирования
logger = logging.getLogger(__name__)

# Базовый URL API Яндекс Диска
YANDEX_DISK_API_BASE_URL = "https://cloud-api.yandex.net/v1/disk/public/resources"


def get_file_list(public_key: str) -> Any | None:
    """
    Получает список файлов по публичному ключу с кэшированием.

    :param public_key: Публичный ключ для доступа к файлам.
    :return: Список файлов или None, если не удалось получить файлы.
    """
    cache_key = f"file_list_{public_key}"
    cached_files = cache.get(cache_key)

    # Логирование кэшированных данных
    logger.debug(f"Кэшированные файлы для {public_key}: {cached_files}")

    if cached_files is not None:
        return cached_files

    params = {'public_key': public_key}
    response = requests.get(YANDEX_DISK_API_BASE_URL, params=params)
    if response.status_code == 200:
        files = response.json().get('_embedded', {}).get('items', [])
        # Логирование полученных файлов
        logger.debug(f"Полученные файлы с Яндекс Диска: {files}")
        cache.set(cache_key, files, timeout=600)  # Кэшируем файлы на 10 минут
        return files
    return None


def download_file(public_key: str, path: str) -> BytesIO | None:
    """
    Скачивает файл по заданному пути и публичному ключу.

    :param public_key: Публичный ключ для доступа к файлу.
    :param path: Путь к файлу на Яндекс Диске.
    :return: Содержимое файла в виде BytesIO или None, если файл не найден.
    """
    params = {'public_key': public_key, 'path': path}
    response = requests.get(f"{YANDEX_DISK_API_BASE_URL}/download", params=params)
    if response.status_code == 200:
        download_url = response.json().get('href')
        file_response = requests.get(download_url)
        return BytesIO(file_response.content)
    return None


def index(request) -> HttpResponse:
    """
    Обрабатывает запросы на главную страницу.

    :param request: HTTP запрос.
    :return: HTTP ответ с формой и списком файлов.
    """
    files = []
    if request.method == 'POST':
        form = PublicLinkForm(request.POST)
        if form.is_valid():
            public_key = form.cleaned_data['public_key']
            files = get_file_list(public_key)
            return render(request, 'diskviewer/index.html', {
                'form': form,
                'files': files,
                'public_key': public_key
            })
    else:
        form = PublicLinkForm()
    return render(request, 'diskviewer/index.html', {'form': form})


def get_file_metadata(public_key: str, path: str) -> dict | None:
    """
    Получает метаданные файла по публичному ключу и пути.

    :param public_key: Публичный ключ для доступа к файлу.
    :param path: Путь к файлу на Яндекс Диске.
    :return: Метаданные файла в виде словаря или None, если файл не найден.
    """
    params = {'public_key': public_key, 'path': path}
    response = requests.get(YANDEX_DISK_API_BASE_URL, params=params)
    if response.status_code == 200:
        return response.json()
    return None


def download(request) -> HttpResponse:
    """
    Обрабатывает запрос на скачивание одного файла.

    :param request: HTTP запрос.
    :return: HTTP ответ с файлом или ошибкой.
    """
    public_key = request.GET.get('public_key')
    file_path = request.GET.get('file_path')

    # Получение метаданных файла
    file_metadata = get_file_metadata(public_key, file_path)
    if file_metadata is None:
        return JsonResponse({'error': 'Файл не найден'}, status=404)

    file_name = file_metadata.get('name', 'downloaded_file')

    # Кодирование имени файла
    encoded_file_name = quote(file_name)

    # Скачивание содержимого файла
    file_content = download_file(public_key, file_path)
    if file_content:
        response = HttpResponse(file_content.getvalue(),
                                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = f'attachment; filename="{encoded_file_name}"'
        return response

    return JsonResponse({'error': 'Файл не найден'}, status=404)


def download_multiple(request) -> HttpResponse:
    """
    Обрабатывает запрос на скачивание нескольких файлов и их упаковку в zip-архив.

    :param request: HTTP запрос.
    :return: HTTP ответ с zip-архивом или ошибкой.
    """
    public_key = request.GET.get('public_key')
    file_paths = request.GET.getlist('file_paths')  # Получаем пути к нескольким файлам из GET параметров

    if not file_paths:
        return JsonResponse({'error': 'Не выбраны файлы'}, status=400)

    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
        for file_path in file_paths:
            file_metadata = get_file_metadata(public_key, file_path)
            if file_metadata is None:
                return JsonResponse({'error': f'Файл не найден: {file_path}'}, status=404)

            file_name = file_metadata.get('name', 'downloaded_file')
            file_content = download_file(public_key, file_path)
            if file_content:
                zip_file.writestr(file_name, file_content.getvalue())
            else:
                return JsonResponse({'error': f'Не удалось скачать файл: {file_name}'}, status=404)

    zip_buffer.seek(0)  # Переход к началу буфера BytesIO
    response = HttpResponse(zip_buffer.getvalue(), content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="downloaded_files.zip"'
    return response
