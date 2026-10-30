# Sample pair

`botanical_rgb.png` and `botanical_depth.png` are an original, synthetic botanical still life drawn for this project. They are not a photograph or estimated depth. The depth map is paired exactly to the illustrated geometry.

Use **Try the sample scene** or upload the two PNGs. Choose **Bright = Near**, focus **0.22**, range **0.18**. The foreground vase and leaves should retain their rib/vein detail while the distant wall, lights and book stack become defocused. Move focus to **1.00** to sharpen the wall instead.

Recreate both assets with `python sample_images/generate_sample.py`. App startup does not require sample files; user uploads work independently.

For real photos, supply a registered grayscale relative-depth map from a camera, dataset, or depth estimation tool. A false-color visualization is not a scalar depth map: convert it using its original colormap or export grayscale depth.
