import math


# This class holds frame and subframe data for a single vector shape.
# Instead of requesting a specific frame by number, a number between frames can be provided and a shape will be returned interpolated between the two adjacent frames.
class Vector_sprite:
    def __init__(self, data):
        # The raw data is a list of tuples of tuples - each tuple within the list is one keyframe, and each tuple within that is a point in the shape.
        self.frames = data
        self.num_frames = len(data)
        self.num_points = len(data[0])
        self.working_frames = {}

    # As new interpolated frames are generated they are cached in a dictionary.
    # When a frame is requested, this method checks the dictionary and returns the relevant shape if present, and if not generates it.
    def get_frame(self, t):
        if self.num_frames == 1:
            t = 0

        if t not in self.working_frames:
            t %= self.num_frames * 100
            if t % 100 == 0:
                self.working_frames[int(t)] = self.get_frame_int(int(t))
            else:
                self.working_frames[int(t)] = self.get_frame_float(int(t))

        return self.working_frames[int(t)]

    # If the frame number requested is one of the keyframes (t is a multiple of 100), just return a shape made up of the points of that keyframe
    @micropython.viper
    def get_frame_int(self, frame):
        frame = round(frame * 0.01)
        data = self.frames[int(frame)]
        path = []
        for point in data:
            path.append(vec2(point[0], point[1]))
        return shape.custom(path)

    # If the frame requested is between keyframes, get the keyframe before and after and return a shape where each point is lerped between the two adjacent keyframes.
    @micropython.viper
    def get_frame_float(self, frame):
        frame *= 0.01
        prev_frame = math.floor(frame)
        next_frame = math.ceil(frame)
        t = frame - prev_frame
        prev_frame %= self.num_frames
        next_frame %= self.num_frames
        prev_data = self.frames[prev_frame]
        next_data = self.frames[next_frame]
        path = []

        for i in range(int(self.num_points)):
            prev_point = vec2(prev_data[i][0], prev_data[i][1])
            next_point = vec2(next_data[i][0], next_data[i][1])
            path.append(vector_lerp(prev_point, next_point, t))

        return shape.custom(path)


@micropython.native
def vector_lerp(point_a, point_b, t):
    int_vector = point_b - point_a
    lerped_vector = int_vector * t
    return point_a + lerped_vector
