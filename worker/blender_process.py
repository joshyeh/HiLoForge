import argparse
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


# -------------------------
# Utilities / safety helpers
# -------------------------

def clear_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def force_object_mode():
    try:
        bpy.ops.object.mode_set(mode="OBJECT")
    except Exception:
        pass


def deselect_all():
    try:
        bpy.ops.object.select_all(action="DESELECT")
    except Exception:
        pass


def set_active(obj):
    bpy.context.view_layer.objects.active = obj

def set_if_exists(obj, prop, value):
    if hasattr(obj, prop):
        setattr(obj, prop, value)

def select(obj, state=True):
    obj.select_set(state)


def mesh_counts(obj):
    me = obj.data
    return len(me.vertices), len(me.polygons)


def import_model(path: str):
    ext = Path(path).suffix.lower()
    if ext in [".glb", ".gltf"]:
        bpy.ops.import_scene.gltf(filepath=path)
    elif ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=path)
    elif ext == ".obj":
        bpy.ops.import_scene.obj(filepath=path)
    else:
        raise RuntimeError(f"Unsupported import extension: {ext}")


def find_main_mesh():
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    if not meshes:
        raise RuntimeError("No mesh objects found in the imported file.")
    meshes.sort(key=lambda o: len(o.data.polygons), reverse=True)
    return meshes[0]


def apply_transforms(obj):
    force_object_mode()
    obj.hide_set(False)
    obj.hide_viewport = False

    deselect_all()
    select(obj, True)
    set_active(obj)

    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)

    select(obj, False)


def triangulate(obj):
    force_object_mode()
    deselect_all()
    select(obj, True)
    set_active(obj)

    tri = obj.modifiers.new(name="Triangulate", type="TRIANGULATE")
    bpy.ops.object.modifier_apply(modifier=tri.name)

    select(obj, False)


def decimate_to_target(obj, target_tris: int):
    force_object_mode()
    current_faces = len(obj.data.polygons)
    if current_faces <= 0:
        return

    # If target >= source, do nothing
    if target_tris >= current_faces:
        return

    ratio = max(0.01, min(1.0, target_tris / float(current_faces)))

    deselect_all()
    select(obj, True)
    set_active(obj)

    mod = obj.modifiers.new(name="Decimate", type="DECIMATE")
    mod.decimate_type = "COLLAPSE"
    mod.ratio = ratio
    set_if_exists(mod, "use_collapse_triangulate", True)
    set_if_exists(mod, "use_preserve_volume", True)

    bpy.ops.object.modifier_apply(modifier=mod.name)

    select(obj, False)


def fill_holes(obj, max_sides=50):
    """
    Fills boundary holes on the LOW mesh after decimation.
    Good for scans that aren’t watertight.
    """
    force_object_mode()
    deselect_all()
    select(obj, True)
    set_active(obj)

    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    # Fill holes up to max_sides boundary size
    bpy.ops.mesh.fill_holes(sides=max_sides)
    bpy.ops.object.mode_set(mode="OBJECT")

    select(obj, False)


def recalc_normals(obj):
    """
    Recalculate normals to reduce shading artifacts after decimation.
    """
    force_object_mode()
    deselect_all()
    select(obj, True)
    set_active(obj)

    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode="OBJECT")

    select(obj, False)

def set_shade_smooth(obj):
    force_object_mode()
    deselect_all()
    select(obj, True)
    set_active(obj)
    bpy.ops.object.shade_smooth()
    select(obj, False)


def set_auto_smooth(obj, angle_deg=60.0):
    if hasattr(obj.data, "use_auto_smooth"):
        if angle_deg <= 0:
            obj.data.use_auto_smooth = False
            return
        obj.data.use_auto_smooth = True
        obj.data.auto_smooth_angle = math.radians(angle_deg)


def shrinkwrap_to_high(low_obj, high_obj, offset=0.0):
    """
    Conform low mesh to high surface to reduce bake misses.
    """
    if offset <= 0:
        return
    force_object_mode()
    deselect_all()
    select(low_obj, True)
    set_active(low_obj)

    mod = low_obj.modifiers.new(name="Shrinkwrap", type="SHRINKWRAP")
    mod.target = high_obj
    mod.wrap_method = "NEAREST_SURFACEPOINT"
    mod.offset = offset
    mod.use_negative_direction = True
    mod.use_positive_direction = True

    bpy.ops.object.modifier_apply(modifier=mod.name)
    select(low_obj, False)


def duplicate_object(obj, new_name: str):
    """
    Duplicate object + mesh data (so HIGH and LOW are independent).
    """
    dup = obj.copy()
    dup.data = obj.data.copy()
    dup.name = new_name
    bpy.context.collection.objects.link(dup)
    return dup


# -------------------------
# UV + Material + Baking
# -------------------------

def smart_uv_unwrap(obj, angle_limit_deg=66.0, island_margin=0.04):
    """
    Creates a fresh UV map on LOW and unwraps it.
    """
    force_object_mode()
    deselect_all()
    select(obj, True)
    set_active(obj)

    # Ensure it has a UV map
    me = obj.data
    if not me.uv_layers:
        me.uv_layers.new(name="UVMap")
    me.uv_layers.active = me.uv_layers[0]

    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(
        angle_limit=angle_limit_deg,
        island_margin=island_margin,
        area_weight=0.0,
        correct_aspect=True
    )
    bpy.ops.object.mode_set(mode="OBJECT")

    select(obj, False)


def ensure_cycles_device(prefer_gpu=True):
    """
    Baking uses Cycles. Prefer GPU (OptiX/CUDA) when available, else CPU.
    """
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"

    if not prefer_gpu:
        scene.cycles.device = "CPU"
        print("INFO: Cycles device set to CPU (GPU disabled by config).")
        return

    # Try to enable GPU devices if the Cycles addon is available
    try:
        cycles_prefs = bpy.context.preferences.addons["cycles"].preferences
    except Exception:
        scene.cycles.device = "CPU"
        print("INFO: Cycles addon not found; using CPU.")
        return

    # Prefer OptiX for RTX, then CUDA
    for compute_type in ("OPTIX", "CUDA"):
        try:
            cycles_prefs.compute_device_type = compute_type
            cycles_prefs.get_devices()

            # Enable all non-CPU devices
            for d in cycles_prefs.devices:
                if d.type != "CPU":
                    d.use = True

            if any(d.use and d.type != "CPU" for d in cycles_prefs.devices):
                scene.cycles.device = "GPU"
                print(f"INFO: Cycles device set to GPU ({compute_type}).")
                return
        except Exception:
            continue

    # Fallback to CPU if no GPU devices found
    scene.cycles.device = "CPU"
    print("INFO: Cycles GPU not available; using CPU.")


def ensure_preview_render_settings(resolution=1024, engine="CYCLES"):
    scene = bpy.context.scene
    if scene.world is None:
        scene.world = bpy.data.worlds.new("PreviewWorld")
    if engine == "CYCLES":
        scene.render.engine = "CYCLES"
        scene.cycles.samples = 16
        scene.cycles.use_denoising = True
    else:
        # Blender 4.x uses BLENDER_EEVEE_NEXT
        scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = resolution
    scene.render.resolution_y = resolution
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    # Light grey background for previews
    scene.world.use_nodes = True
    nodes = scene.world.node_tree.nodes
    bg = nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = (0.82, 0.82, 0.82, 1.0)
        bg.inputs["Strength"].default_value = 1.0


def get_or_create_camera(name="PreviewCam"):
    cam = bpy.data.objects.get(name)
    if cam and cam.type == "CAMERA":
        return cam
    cam_data = bpy.data.cameras.new(name)
    cam = bpy.data.objects.new(name, cam_data)
    bpy.context.collection.objects.link(cam)
    return cam


def get_or_create_light(name, energy, location):
    light = bpy.data.objects.get(name)
    if light and light.type == "LIGHT":
        return light
    light_data = bpy.data.lights.new(name=name, type="AREA")
    light_data.energy = energy
    light = bpy.data.objects.new(name, light_data)
    light.location = location
    bpy.context.collection.objects.link(light)
    return light


def look_at(camera, target):
    direction = target - camera.location
    rot_quat = direction.to_track_quat("-Z", "Y")
    camera.rotation_euler = rot_quat.to_euler()


def frame_camera_to_object(camera, obj):
    bbox_world = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    center = sum(bbox_world, Vector()) / 8.0
    max_dim = max((v - center).length for v in bbox_world)
    dist = max(1.0, max_dim * 2.2)
    camera.location = center + Vector((dist * 0.6, -dist, dist * 0.7))
    look_at(camera, center)
    return center


def render_preview(obj, output_path: Path, resolution=1024, image_override=None):
    ensure_preview_render_settings(resolution=resolution, engine="CYCLES")
    ensure_cycles_device()
    force_object_mode()

    # Optional override material (emission) for reliable preview
    original_mats = None
    temp_mat = None
    if image_override is not None:
        original_mats = list(obj.data.materials)
        temp_mat = bpy.data.materials.new(name="preview_emission")
        temp_mat.use_nodes = True
        nodes = temp_mat.node_tree.nodes
        links = temp_mat.node_tree.links
        for n in list(nodes):
            nodes.remove(n)
        out = nodes.new(type="ShaderNodeOutputMaterial")
        out.location = (200, 0)
        emission = nodes.new(type="ShaderNodeEmission")
        emission.location = (0, 0)
        tex = nodes.new(type="ShaderNodeTexImage")
        tex.location = (-250, 0)
        if isinstance(image_override, (str, Path)):
            img_path = str(image_override)
            tex.image = bpy.data.images.load(img_path, check_existing=True)
        else:
            tex.image = image_override
        emission.inputs["Strength"].default_value = 1.2
        links.new(tex.outputs["Color"], emission.inputs["Color"])
        links.new(emission.outputs["Emission"], out.inputs["Surface"])
        obj.data.materials.clear()
        obj.data.materials.append(temp_mat)

    # Mild exposure lift for consistency
    bpy.context.scene.view_settings.exposure = 0.6

    # Cache visibility state
    vis_state = {}
    for o in bpy.context.scene.objects:
        vis_state[o.name] = (o.hide_viewport, o.hide_render, o.hide_get())

    # Hide everything except target
    for o in bpy.context.scene.objects:
        is_target = o.name == obj.name
        o.hide_viewport = not is_target
        o.hide_render = not is_target
        o.hide_set(not is_target)

    cam = get_or_create_camera()
    center = frame_camera_to_object(cam, obj)
    bpy.context.scene.camera = cam

    # Basic 2-light setup
    get_or_create_light("PreviewKey", 1200, cam.location + Vector((0.8, -0.2, 0.4)))
    get_or_create_light("PreviewFill", 400, center + Vector((-1.5, 2.0, 1.5)))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.scene.render.filepath = str(output_path)
    bpy.ops.render.render(write_still=True)

    # Restore visibility
    for o in bpy.context.scene.objects:
        if o.name in vis_state:
            o.hide_viewport, o.hide_render, hidden = vis_state[o.name]
            o.hide_set(hidden)

    # Restore original materials
    if original_mats is not None:
        obj.data.materials.clear()
        for m in original_mats:
            obj.data.materials.append(m)
        if temp_mat is not None:
            try:
                bpy.data.materials.remove(temp_mat, do_unlink=True)
            except Exception:
                pass


def predecimation_remesh(obj, voxel_size=0.0):
    """
    Optional voxel remesh to regularize topology before decimation.
    """
    if voxel_size <= 0:
        return
    force_object_mode()
    deselect_all()
    select(obj, True)
    set_active(obj)

    mod = obj.modifiers.new(name="PreRemesh", type="REMESH")
    mod.mode = "VOXEL"
    mod.voxel_size = voxel_size
    mod.use_smooth_shade = True
    mod.use_remove_disconnected = False
    bpy.ops.object.modifier_apply(modifier=mod.name)

    select(obj, False)


def make_bake_image(name: str, size: int):
    img = bpy.data.images.new(name=name, width=size, height=size, alpha=True, float_buffer=False)
    img.generated_color = (0.0, 0.0, 0.0, 1.0)
    return img


def build_low_material_with_images(low_obj, basecolor_img, normal_img):
    """
    Creates a clean Principled material on LOW that uses the baked atlas textures.
    """
    mat = bpy.data.materials.new(name="mat_atlas")
    mat.use_nodes = True
    nt = mat.node_tree
    nodes = nt.nodes
    links = nt.links

    # Clear default nodes
    for n in list(nodes):
        nodes.remove(n)

    out = nodes.new(type="ShaderNodeOutputMaterial")
    out.location = (400, 0)

    principled = nodes.new(type="ShaderNodeBsdfPrincipled")
    principled.location = (150, 0)
    links.new(principled.outputs["BSDF"], out.inputs["Surface"])

    # BaseColor atlas
    tex_base = nodes.new(type="ShaderNodeTexImage")
    tex_base.location = (-450, 120)
    tex_base.image = basecolor_img
    tex_base.interpolation = "Smart"
    links.new(tex_base.outputs["Color"], principled.inputs["Base Color"])

    # Normal atlas
    tex_norm = nodes.new(type="ShaderNodeTexImage")
    tex_norm.location = (-450, -180)
    tex_norm.image = normal_img
    tex_norm.image.colorspace_settings.name = "Non-Color"
    tex_norm.interpolation = "Smart"

    normal_node = nodes.new(type="ShaderNodeNormalMap")
    normal_node.location = (-150, -180)
    links.new(tex_norm.outputs["Color"], normal_node.inputs["Color"])
    links.new(normal_node.outputs["Normal"], principled.inputs["Normal"])

    # Assign material to LOW
    if low_obj.data.materials:
        low_obj.data.materials[0] = mat
    else:
        low_obj.data.materials.append(mat)

    return mat, tex_base, tex_norm


def has_basecolor_texture(obj) -> bool:
    """
    Returns True if any material on the object has a Base Color texture input.
    """
    for mat in obj.data.materials:
        if not mat or not mat.use_nodes:
            continue
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        for node in nodes:
            if node.type == "BSDF_PRINCIPLED":
                base_input = node.inputs.get("Base Color")
                if base_input and base_input.is_linked:
                    for link in links:
                        if link.to_socket == base_input and link.from_node.type == "TEX_IMAGE":
                            return True
    return False


def fill_image_solid(img, rgba):
    img.generated_color = rgba
    # Ensure pixels are filled for viewers that ignore generated_color
    try:
        img.pixels = list(rgba) * (img.size[0] * img.size[1])
    except Exception:
        pass


def make_temp_bake_node(mat, image, label):
    """
    Create an unconnected image node for baking to avoid circular dependencies.
    """
    nt = mat.node_tree
    node = nt.nodes.new(type="ShaderNodeTexImage")
    node.location = (-900, -420)
    node.image = image
    node.label = label
    node.name = label
    return node


def remove_node_safe(mat, node):
    try:
        mat.node_tree.nodes.remove(node)
    except Exception:
        pass


def set_active_image_node(mat, image_node):
    """
    Cycles baking writes into the *active* image texture node on the active object.
    """
    for n in mat.node_tree.nodes:
        n.select = False
    image_node.select = True
    mat.node_tree.nodes.active = image_node


def bake_normal(high_obj, low_obj, normal_img, ray_distance=0.02, bake_margin=4, cage_extrusion=0.0):
    ensure_cycles_device()
    force_object_mode()

    scene = bpy.context.scene
    scene.cycles.bake_type = "NORMAL"
    scene.render.bake.use_selected_to_active = True
    scene.render.bake.use_cage = cage_extrusion > 0.0
    scene.render.bake.cage_extrusion = cage_extrusion
    scene.render.bake.max_ray_distance = ray_distance
    scene.render.bake.normal_space = "TANGENT"
    scene.render.bake.margin = bake_margin

    # Ensure both objects are in the active view layer
    vl = bpy.context.view_layer
    if high_obj.name not in vl.objects:
        vl.layer_collection.collection.objects.link(high_obj)
    if low_obj.name not in vl.objects:
        vl.layer_collection.collection.objects.link(low_obj)

    # Make sure both are visible/selectable/renderable
    high_obj.hide_set(False); high_obj.hide_viewport = False; high_obj.hide_render = False
    low_obj.hide_set(False);  low_obj.hide_viewport = False; low_obj.hide_render = False

    # Selection order: select HIGH, select LOW, active LOW
    deselect_all()
    high_obj.select_set(True)
    low_obj.select_set(True)
    bpy.context.view_layer.objects.active = low_obj

    # Bake into the active image node on LOW (you already set it)
    bpy.ops.object.bake(type="NORMAL")


def bake_basecolor(high_obj, low_obj, mat, image_node, ray_distance=0.02, bake_margin=4, cage_extrusion=0.0):
    """
    Bake diffuse color only (no lighting) into the LOW active image.
    """
    ensure_cycles_device()
    force_object_mode()

    scene = bpy.context.scene
    scene.cycles.bake_type = "DIFFUSE"
    scene.render.bake.use_selected_to_active = True
    scene.render.bake.max_ray_distance = ray_distance
    scene.render.bake.margin = bake_margin
    scene.render.bake.use_cage = cage_extrusion > 0.0
    scene.render.bake.cage_extrusion = cage_extrusion

    # Bake ONLY color
    scene.render.bake.use_pass_direct = False
    scene.render.bake.use_pass_indirect = False
    scene.render.bake.use_pass_color = True

    # Make sure both are visible/selectable/renderable
    high_obj.hide_set(False); high_obj.hide_viewport = False; high_obj.hide_render = False
    low_obj.hide_set(False);  low_obj.hide_viewport = False; low_obj.hide_render = False

    deselect_all()
    select(high_obj, True)
    select(low_obj, True)
    set_active(low_obj)

    # Ensure the correct image node is active for baking
    set_active_image_node(mat, image_node)

    bpy.ops.object.bake(type="DIFFUSE")

    ##TODO: Add Multi LODS



def save_image(img, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    img.filepath_raw = str(path)
    img.file_format = "PNG"
    img.save()


def export_glb(output_path: str):
    bpy.ops.export_scene.gltf(
        filepath=output_path,
        export_format="GLB",
        export_apply=True,
        export_yup=True,
        # Keep these minimal and widely supported
        export_texcoords=True,
        export_normals=True,
        export_materials="EXPORT",
    )


# -------------------------
# Main
# -------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output_dir", required=True)
    parser.add_argument("--target_tris", type=int, default=5000)
    parser.add_argument("--tex_size", type=int, default=4096)
    parser.add_argument("--ray_distance", type=float, default=0.02)
    parser.add_argument("--island_margin", type=float, default=0.06)
    parser.add_argument("--bake_margin", type=int, default=12)
    parser.add_argument("--cage_extrusion", type=float, default=0.06)
    parser.add_argument("--shrinkwrap_offset", type=float, default=0.0)
    parser.add_argument("--remesh_voxel_size", type=float, default=0.0)
    parser.add_argument("--auto_smooth_angle", type=float, default=0.0)
    args = parser.parse_args()

    input_path = args.input
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    textures_dir = output_dir / "textures"
    textures_dir.mkdir(parents=True, exist_ok=True)

    clear_scene()
    import_model(input_path)

    src = find_main_mesh()
    apply_transforms(src)

    # Create HIGH and LOW
    high = duplicate_object(src, "HIGH")
    low = duplicate_object(src, "LOW")

    # Hide HIGH from export (optional)
    high.hide_render = True
    high.hide_viewport = True

    # Prep both for predictable processing
    triangulate(high)
    triangulate(low)

    v0, f0 = mesh_counts(low)

    # Optional remesh before decimation (regularize topology)
    predecimation_remesh(low, voxel_size=args.remesh_voxel_size)

    # Decimate LOW (only if target < source)
    decimate_to_target(low, args.target_tris)
    fill_holes(low, max_sides=50)
    recalc_normals(low)
    set_shade_smooth(low)
    set_auto_smooth(low, angle_deg=args.auto_smooth_angle)
    shrinkwrap_to_high(low, high, offset=args.shrinkwrap_offset)

    v1, f1 = mesh_counts(low)

    # UV unwrap LOW for atlas baking
    smart_uv_unwrap(low, angle_limit_deg=66.0, island_margin=args.island_margin)

    # Create bake images
    base_img = make_bake_image("atlas_basecolor", args.tex_size)
    norm_img = make_bake_image("atlas_normal", args.tex_size)

    # Build a clean material on LOW, and make the bake targets active
    mat, tex_base_node, tex_norm_node = build_low_material_with_images(low, base_img, norm_img)

    # Bake BaseColor into base_img using a temp unconnected node (avoid circular dependency)
    if has_basecolor_texture(high):
        temp_base_node = make_temp_bake_node(mat, base_img, "TEMP_BAKE_BASE")
        set_active_image_node(mat, temp_base_node)
        bake_basecolor(
            high,
            low,
            mat,
            temp_base_node,
            ray_distance=args.ray_distance,
            bake_margin=args.bake_margin,
            cage_extrusion=args.cage_extrusion,
        )
        remove_node_safe(mat, temp_base_node)
    else:
        # Fallback: neutral gray when no base color texture is present
        fill_image_solid(base_img, (0.5, 0.5, 0.5, 1.0))

    # Bake Normal into norm_img
    temp_norm_node = make_temp_bake_node(mat, norm_img, "TEMP_BAKE_NORM")
    set_active_image_node(mat, temp_norm_node)
    bake_normal(
        high,
        low,
        norm_img,
        ray_distance=args.ray_distance,
        bake_margin=args.bake_margin,
        cage_extrusion=args.cage_extrusion,
    )
    remove_node_safe(mat, temp_norm_node)

    # Save textures (even though we embed, it’s nice to have files too)
    save_image(base_img, textures_dir / "atlas_basecolor.png")
    save_image(norm_img, textures_dir / "atlas_normal.png")
    norm_img.pack()

    # Preview renders (before + after)
    preview_before = output_dir / "preview_before.png"
    preview_after = output_dir / "preview_after.png"
    try:
        print("INFO: Rendering preview_before...")
        render_preview(high, preview_before, resolution=1024)
    except Exception as e:
        print(f"WARNING: preview_before failed: {e}")
    try:
        print("INFO: Rendering preview_after...")
        render_preview(
            low,
            preview_after,
            resolution=1024,
            image_override=textures_dir / "atlas_basecolor.png",
        )
    except Exception as e:
        print(f"WARNING: preview_after failed: {e}")

    # Remove original src object from export to avoid duplicates
    try:
        bpy.data.objects.remove(src, do_unlink=True)
    except Exception:
        pass

    out_glb = output_dir / "model_low.glb"
    # Export only LOW to avoid including the original/high mesh
    force_object_mode()
    deselect_all()
    # Remove any other mesh objects before export
    for o in list(bpy.context.scene.objects):
        if o.type == "MESH" and o.name != low.name:
            try:
                bpy.data.objects.remove(o, do_unlink=True)
            except Exception:
                pass
    low.hide_set(False)
    low.hide_viewport = False
    low.hide_render = False
    export_glb(str(out_glb))

    # Manifest / stats
    manifest = output_dir / "manifest.txt"
    manifest.write_text(
        f"input={input_path}\n"
        f"target_tris={args.target_tris}\n"
        f"tex_size={args.tex_size}\n"
        f"ray_distance={args.ray_distance}\n"
        f"island_margin={args.island_margin}\n"
        f"bake_margin={args.bake_margin}\n"
        f"cage_extrusion={args.cage_extrusion}\n"
        f"shrinkwrap_offset={args.shrinkwrap_offset}\n"
        f"remesh_voxel_size={args.remesh_voxel_size}\n"
        f"auto_smooth_angle={args.auto_smooth_angle}\n"
        f"before_low: verts={v0} faces={f0}\n"
        f"after_low:  verts={v1} faces={f1}\n"
        f"textures=atlas_basecolor.png, atlas_normal.png\n"
        f"previews=preview_before.png, preview_after.png\n"
        f"export=model_low.glb\n"
    )

    print(f"OK: exported {out_glb}")
    print(f"STATS: before verts={v0} faces={f0} | after verts={v1} faces={f1}")


if __name__ == "__main__":
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    else:
        argv = []
    sys.argv = [sys.argv[0]] + argv
    main()



