# Generated by Django 5.0.6 on 2024-09-03 11:50

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('registration', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='tenant',
            name='user',
        ),
    ]
