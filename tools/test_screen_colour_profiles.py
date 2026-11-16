import unittest
import numpy as np
from zoom_import.colour_profiles import colours, PROFILES


class ColourTests(unittest.TestCase):
    def test_white_magenta_and_inverse(self):
        # BGR: magenta, white, blue, black, yellow.
        frame=np.array([[[255,0,255],[255,255,255],[255,0,0],[0,0,0],[0,255,255]]],dtype=np.uint8)
        active,base=colours(frame,PROFILES['white-magenta'])
        self.assertEqual(active.tolist(),[[True,False,False,False,False]])
        self.assertEqual(base.tolist(),[[False,True,False,False,False]])
        active,base=colours(frame,PROFILES['magenta-white'])
        self.assertEqual(active.tolist(),[[False,True,False,False,False]])
        self.assertEqual(base.tolist(),[[True,False,False,False,False]])

    def test_zoom_profiles_keep_previous_detection(self):
        frame=np.array([[[255,0,0],[255,255,255],[0,255,255],[255,0,255]]],dtype=np.uint8)
        active,base=colours(frame,PROFILES['white-blue'])
        self.assertEqual(active.tolist(),[[True,False,False,False]])
        self.assertEqual(base.tolist(),[[False,True,False,False]])
        active,base=colours(frame,PROFILES['blue-yellow'])
        self.assertEqual(active.tolist(),[[False,False,True,False]])
        self.assertEqual(base.tolist(),[[True,False,False,True]])


if __name__=='__main__':unittest.main()
