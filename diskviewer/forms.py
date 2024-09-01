from django import forms


class PublicLinkForm(forms.Form):
    public_key = forms.CharField(label='Публичная ссылка', max_length=255)
