import logging
from urllib.parse import quote
from django.core.cache import cache
from django.shortcuts import render
from django.http import HttpResponse, JsonResponse
from .forms import PublicLinkForm
import requests
from io import BytesIO
import zipfile

logger = logging.getLogger(__name__)

YANDEX_DISK_API_BASE_URL = "https://cloud-api.yandex.net/v1/disk/public/resources"


def get_file_list(public_key: str):
    cache_key = f"file_list_{public_key}"
    cached_files = cache.get(cache_key)

    logger.debug(f"Cached files for {public_key}: {cached_files}")

    if cached_files is not None:
        return cached_files

    params = {'public_key': public_key}
    response = requests.get(YANDEX_DISK_API_BASE_URL, params=params)
    if response.status_code == 200:
        files = response.json().get('_embedded', {}).get('items', [])
        logger.debug(f"Fetched files from Yandex Disk: {files}")
        cache.set(cache_key, files, timeout=600)
        return files
    return None


def download_file(public_key: str, path: str):
    params = {'public_key': public_key, 'path': path}
    response = requests.get(f"{YANDEX_DISK_API_BASE_URL}/download", params=params)
    if response.status_code == 200:
        download_url = response.json().get('href')
        file_response = requests.get(download_url)
        return BytesIO(file_response.content)
    return None


def index(request):
    files = []
    if request.method == 'POST':
        form = PublicLinkForm(request.POST)
        if form.is_valid():
            public_key = form.cleaned_data['public_key']
            files = get_file_list(public_key)
            return render(request, 'diskviewer/index.html', {'form': form, 'files': files, 'public_key': public_key})
    else:
        form = PublicLinkForm()
    return render(request, 'diskviewer/index.html', {'form': form})


def get_file_metadata(public_key: str, path: str):
    params = {'public_key': public_key, 'path': path}
    response = requests.get(YANDEX_DISK_API_BASE_URL, params=params)
    if response.status_code == 200:
        return response.json()
    return None


def download(request):
    public_key = request.GET.get('public_key')
    file_path = request.GET.get('file_path')

    file_metadata = get_file_metadata(public_key, file_path)
    if file_metadata is None:
        return JsonResponse({'error': 'File not found'}, status=404)

    file_name = file_metadata.get('name', 'downloaded_file')

    # Ensure the filename is correctly encoded
    encoded_file_name = quote(file_name)

    file_content = download_file(public_key, file_path)
    if file_content:
        response = HttpResponse(file_content.getvalue(),
                                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = f'attachment; filename="{encoded_file_name}"'
        return response

    return JsonResponse({'error': 'File not found'}, status=404)


def download_multiple(request):
    public_key = request.GET.get('public_key')
    file_paths = request.GET.getlist('file_paths')  # Get multiple file paths from GET parameters

    if not file_paths:
        return JsonResponse({'error': 'No files selected'}, status=400)

    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
        for file_path in file_paths:
            file_metadata = get_file_metadata(public_key, file_path)
            if file_metadata is None:
                return JsonResponse({'error': f'File not found: {file_path}'}, status=404)

            file_name = file_metadata.get('name', 'downloaded_file')
            file_content = download_file(public_key, file_path)
            if file_content:
                zip_file.writestr(file_name, file_content.getvalue())
            else:
                return JsonResponse({'error': f'Could not download file: {file_name}'}, status=404)

    zip_buffer.seek(0)  # Go to the beginning of the BytesIO buffer
    response = HttpResponse(zip_buffer.getvalue(), content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="downloaded_files.zip"'
    return response
