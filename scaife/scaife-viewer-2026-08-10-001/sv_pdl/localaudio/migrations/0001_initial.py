from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []

    operations = [
        migrations.CreateModel(
            name="AudioPackage",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("slug", models.SlugField(max_length=80, unique=True)),
                ("label", models.CharField(max_length=200)),
                ("license", models.CharField(max_length=80)),
                ("attribution", models.TextField(blank=True)),
                ("source_url", models.CharField(blank=True, max_length=300)),
                ("root_dir", models.CharField(max_length=200)),
                ("clip_count", models.PositiveIntegerField(default=0)),
            ],
        ),
        migrations.CreateModel(
            name="AudioClip",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("version_urn", models.CharField(max_length=200)),
                ("ref", models.CharField(max_length=40)),
                ("ref_key", models.CharField(max_length=120)),
                ("path", models.CharField(max_length=400)),
                ("package", models.ForeignKey(
                    on_delete=models.deletion.CASCADE,
                    related_name="clips",
                    to="localaudio.audiopackage",
                )),
            ],
            options={
                "ordering": ["ref_key", "id"],
            },
        ),
        migrations.AddIndex(
            model_name="audioclip",
            index=models.Index(
                fields=["version_urn", "ref_key"], name="localaudio_clip_ref_idx"
            ),
        ),
        migrations.AddConstraint(
            model_name="audioclip",
            constraint=models.UniqueConstraint(
                fields=["package", "version_urn", "ref"],
                name="localaudio_clip_unique",
            ),
        ),
    ]
